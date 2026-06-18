from __future__ import annotations

import hashlib
import uuid
import httpx
import pytest
from sqlalchemy import select

from app.database import get_session_factory
from app.dependencies.auth import get_current_user, get_current_user_or_api_key, CurrentUser
from app.main import app
from app.models.api_key import ApiKey


@pytest.mark.asyncio
async def test_api_key_rotation_flow(client: httpx.AsyncClient) -> None:
    """
    Verify the key rotation flow:
    - Admin can create a key.
    - Plaintext key is returned once, only hash is stored in DB.
    - Admin can rotate key. New plaintext key is returned.
    - Old key is invalidated immediately (hash is replaced).
    - Second rotation behaves correctly (invalidates first rotated key, generates a new one).
    """
    factory = get_session_factory()
    async with factory() as db:
        from app.models.org import Org
        from app.models.user import User
        org = (await db.execute(select(Org))).scalars().first()
        user = (await db.execute(select(User))).scalars().first()
        org_id = org.id
        user_id = user.id

    async def mock_admin_auth():
        return CurrentUser(
            user_id=str(user_id),
            email="test-admin@example.com",
            name="test-admin",
            org_id=str(org_id),
            role="platform_admin"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_admin_auth
    app.dependency_overrides[get_current_user] = mock_admin_auth

    try:
        # Create an API key
        create_resp = await client.post("/admin/api-keys", json={"name": "Test Rotation Key"})
        assert create_resp.status_code == 201
        key_data = create_resp.json()
        key_id = key_data["id"]
        old_plaintext = key_data["plaintext_key"]
        
        # Verify hash matches in DB
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key is not None
            assert db_key.key_hash == hashlib.sha256(old_plaintext.encode()).hexdigest()
            # Verify plaintext is not stored in the model at all
            assert not hasattr(db_key, "plaintext_key")

        # 2. Call rotate endpoint
        rotate_resp = await client.post(f"/admin/api-keys/{key_id}/rotate")
        assert rotate_resp.status_code == 200
        rotated_data = rotate_resp.json()
        new_plaintext = rotated_data["plaintext_key"]
        assert new_plaintext != old_plaintext

        # Verify old key is invalid in DB, new key hash is stored
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key.key_hash == hashlib.sha256(new_plaintext.encode()).hexdigest()
            assert db_key.key_hash != hashlib.sha256(old_plaintext.encode()).hexdigest()

        # 3. Call rotate endpoint again (rotate 2nd time)
        rotate_resp_2 = await client.post(f"/admin/api-keys/{key_id}/rotate")
        assert rotate_resp_2.status_code == 200
        rotated_data_2 = rotate_resp_2.json()
        new_plaintext_2 = rotated_data_2["plaintext_key"]
        assert new_plaintext_2 != new_plaintext
        assert new_plaintext_2 != old_plaintext

        # Verify DB is updated to new_plaintext_2 hash
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key.key_hash == hashlib.sha256(new_plaintext_2.encode()).hexdigest()

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_key_rotation_rbac(client: httpx.AsyncClient) -> None:
    """Verify role-based access restrictions block unauthorized key rotation."""
    factory = get_session_factory()
    async with factory() as db:
        from app.models.org import Org
        from app.models.user import User
        org = (await db.execute(select(Org))).scalars().first()
        user = (await db.execute(select(User))).scalars().first()
        org_id = org.id
        user_id = user.id

    # Create key as admin
    async def mock_admin_auth():
        return CurrentUser(
            user_id=str(user_id),
            email="test-admin@example.com",
            name="test-admin",
            org_id=str(org_id),
            role="platform_admin"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_admin_auth
    app.dependency_overrides[get_current_user] = mock_admin_auth
    try:
        create_resp = await client.post("/admin/api-keys", json={"name": "RBAC Test Key"})
        assert create_resp.status_code == 201
        key_id = create_resp.json()["id"]
    finally:
        app.dependency_overrides.clear()

    # Now override auth to be viewer (unauthorized)
    async def mock_viewer_auth():
        return CurrentUser(
            user_id=str(user_id),
            email="test-viewer@example.com",
            name="test-viewer",
            org_id=str(org_id),
            role="viewer"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_viewer_auth
    app.dependency_overrides[get_current_user] = mock_viewer_auth

    try:
        # Call rotate as viewer (should return 403 Forbidden)
        rotate_resp = await client.post(f"/admin/api-keys/{key_id}/rotate")
        assert rotate_resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rate_limiting_headers(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify rate-limiting errors return correct Retry-After and X-RateLimit-Remaining headers."""
    import app.routers.inference as inference_router
    async def mock_check_rate_limit(*args, **kwargs):
        return False, 42
    monkeypatch.setattr(inference_router, "check_rate_limit", mock_check_rate_limit)

    async def mock_user_auth():
        return CurrentUser(
            user_id=str(uuid.uuid4()),
            email="test-user@example.com",
            name="test-user",
            org_id=str(uuid.uuid4()),
            role="operator"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_user_auth
    app.dependency_overrides[get_current_user] = mock_user_auth

    try:
        payload = {
            "model": "gemma2:2b",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "42"
        assert resp.headers.get("X-RateLimit-Remaining") == "0"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_key_revoke_and_delete_flow(client: httpx.AsyncClient) -> None:
    """
    Verify the delete endpoint behavior:
    - Calling DELETE on an active API key sets is_active = False (revokes it).
    - Calling DELETE on an already inactive key removes it from the database.
    """
    factory = get_session_factory()
    async with factory() as db:
        from app.models.org import Org
        from app.models.user import User
        org = (await db.execute(select(Org))).scalars().first()
        user = (await db.execute(select(User))).scalars().first()
        org_id = org.id
        user_id = user.id

    async def mock_admin_auth():
        return CurrentUser(
            user_id=str(user_id),
            email="test-admin@example.com",
            name="test-admin",
            org_id=str(org_id),
            role="platform_admin"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_admin_auth
    app.dependency_overrides[get_current_user] = mock_admin_auth

    try:
        # 1. Create an API key
        create_resp = await client.post("/admin/api-keys", json={"name": "Delete Test Key"})
        assert create_resp.status_code == 201
        key_data = create_resp.json()
        key_id = key_data["id"]

        # Verify it exists and is active
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key is not None
            assert db_key.is_active is True

        # 2. Call delete (revoke) first time
        delete_resp = await client.delete(f"/admin/api-keys/{key_id}")
        assert delete_resp.status_code == 204

        # Verify it is now inactive (revoked)
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key is not None
            assert db_key.is_active is False

        # 3. Call delete again (to hard delete)
        delete_resp2 = await client.delete(f"/admin/api-keys/{key_id}")
        assert delete_resp2.status_code == 204

        # Verify it is removed from the database entirely
        async with factory() as db:
            db_key = await db.get(ApiKey, uuid.UUID(key_id))
            assert db_key is None

    finally:
        app.dependency_overrides.clear()
