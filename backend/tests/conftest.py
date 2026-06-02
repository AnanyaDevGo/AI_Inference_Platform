import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.dependencies.auth import get_current_user_or_api_key, CurrentUser

@pytest_asyncio.fixture(autouse=True)
async def clear_db_engine():
    """Dispose of the database engine before and after each test to prevent event loop mismatch."""
    import app.database as db_module
    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None
    yield
    if db_module._engine is not None:
        await db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async test client bound to the FastAPI app with mocked auth and valid DB IDs."""
    from app.database import get_session_factory
    from app.models.org import Org
    from app.models.user import User
    from sqlalchemy import select
    import uuid

    factory = get_session_factory()
    async with factory() as db:
        # Get or create Org
        result_org = await db.execute(select(Org.id))
        org_id = result_org.scalars().first()
        if not org_id:
            org_id = uuid.uuid4()
            test_org = Org(id=org_id, name="Test Org")
            db.add(test_org)
            await db.flush()
        
        # Get or create User
        result_user = await db.execute(select(User.id))
        user_id = result_user.scalars().first()
        if not user_id:
            user_id = uuid.uuid4()
            test_user = User(
                id=user_id,
                org_id=org_id,
                name="Test User",
                email="test-client-fixture@example.com",
                password_hash="mock-hash",
                role="viewer",
                auth_provider="local",
                is_active=True,
                is_verified=True,
                password_set=True
            )
            db.add(test_user)
            await db.flush()
        
        await db.commit()
        org_id_str = str(org_id)
        user_id_str = str(user_id)

    async def mock_auth():
        return CurrentUser(
            user_id=user_id_str,
            email="test-client-fixture@example.com",
            name="test",
            org_id=org_id_str,
            role="viewer"
        )
    app.dependency_overrides[get_current_user_or_api_key] = mock_auth
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def async_client(client) -> AsyncClient:
    """Alias for client fixture to support test_reliability.py."""
    yield client

@pytest.fixture
def token() -> str:
    """Mock token for test_reliability.py."""
    return "mock-token"
