from __future__ import annotations

import uuid
import httpx
import pytest
from sqlalchemy import select

from app.database import get_session_factory
from app.dependencies.auth import get_current_user, get_current_user_or_api_key, CurrentUser
from app.main import app
from app.models.conversation import Conversation, ChatMessage


@pytest.mark.asyncio
async def test_conversations_user_isolation(client: httpx.AsyncClient) -> None:
    """
    Verify strict user isolation and 403 Forbidden responses:
    - User A can create and view their own conversation.
    - User B trying to view User A's conversation receives a 403 Forbidden.
    - User B trying to edit/rename User A's conversation receives a 403 Forbidden.
    - User B trying to delete User A's conversation receives a 403 Forbidden.
    - User B trying to add a message to User A's conversation receives a 403 Forbidden.
    """
    factory = get_session_factory()
    async with factory() as db:
        from app.models.org import Org
        from app.models.user import User
        org = (await db.execute(select(Org))).scalars().first()
        user_list = (await db.execute(select(User))).scalars().all()
        org_id = org.id
        
        # Ensure we have at least 2 distinct user IDs
        user_a_id = user_list[0].id
        user_b_id = uuid.uuid4() # Mock a different user id

    # 1. Authenticate as User A and create a conversation
    async def mock_user_a_auth():
        return CurrentUser(
            user_id=str(user_a_id),
            email="user-a@example.com",
            name="User A",
            org_id=str(org_id),
            role="viewer"
        )
    
    app.dependency_overrides[get_current_user_or_api_key] = mock_user_a_auth
    app.dependency_overrides[get_current_user] = mock_user_a_auth

    try:
        # User A creates a conversation
        create_resp = await client.post("/api/conversations", json={"title": "User A Chat", "model_name": "gemma2:2b"})
        assert create_resp.status_code == 201
        conv_data = create_resp.json()
        conv_id = conv_data["id"]
        
        # User A should be able to get it
        get_resp = await client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "User A Chat"

    finally:
        app.dependency_overrides.clear()

    # 2. Authenticate as User B and try to access User A's conversation
    async def mock_user_b_auth():
        return CurrentUser(
            user_id=str(user_b_id),
            email="user-b@example.com",
            name="User B",
            org_id=str(org_id),
            role="viewer"
        )
    
    app.dependency_overrides[get_current_user_or_api_key] = mock_user_b_auth
    app.dependency_overrides[get_current_user] = mock_user_b_auth

    try:
        # User B tries to GET User A's conversation (should return 403 Forbidden)
        get_resp_b = await client.get(f"/api/conversations/{conv_id}")
        assert get_resp_b.status_code == 403

        # User B tries to RENAME/PATCH User A's conversation (should return 403 Forbidden)
        patch_resp_b = await client.patch(f"/api/conversations/{conv_id}", json={"title": "Hacked Title"})
        assert patch_resp_b.status_code == 403

        # User B tries to ADD a message to User A's conversation (should return 403 Forbidden)
        post_msg_resp = await client.post(f"/api/conversations/{conv_id}/messages", json={"role": "user", "content": "hello"})
        assert post_msg_resp.status_code == 403

        # User B tries to DELETE User A's conversation (should return 403 Forbidden)
        del_resp_b = await client.delete(f"/api/conversations/{conv_id}")
        assert del_resp_b.status_code == 403

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_conversations_pagination(client: httpx.AsyncClient) -> None:
    """Verify that pagination limit and offset work for list conversations."""
    factory = get_session_factory()
    async with factory() as db:
        from app.models.org import Org
        from app.models.user import User
        org = (await db.execute(select(Org))).scalars().first()
        user = (await db.execute(select(User))).scalars().first()
        org_id = org.id
        user_id = user.id

    async def mock_user_auth():
        return CurrentUser(
            user_id=str(user_id),
            email="test-pagination@example.com",
            name="test-user",
            org_id=str(org_id),
            role="viewer"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_user_auth
    app.dependency_overrides[get_current_user] = mock_user_auth

    try:
        # Create 3 conversations
        for i in range(3):
            res = await client.post("/api/conversations", json={"title": f"Chat {i}"})
            assert res.status_code == 201

        # Retrieve with limit=2
        list_resp_1 = await client.get("/api/conversations?limit=2")
        assert list_resp_1.status_code == 200
        data_1 = list_resp_1.json()
        assert len(data_1) == 2

        # Retrieve with limit=2 and offset=2
        list_resp_2 = await client.get("/api/conversations?limit=2&offset=2")
        assert list_resp_2.status_code == 200
        data_2 = list_resp_2.json()
        assert len(data_2) >= 1  # Should find at least the third one created plus any pre-existing ones
        
        # Ensure they are sorted by updated_at descending (Chat 2 first)
        assert data_1[0]["title"] == "Chat 2"
        assert data_1[1]["title"] == "Chat 1"

    finally:
        app.dependency_overrides.clear()
