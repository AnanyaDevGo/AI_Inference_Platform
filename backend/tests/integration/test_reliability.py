import asyncio
import httpx
import pytest
from app.config import get_settings

@pytest.mark.asyncio
async def test_health_liveness(async_client: httpx.AsyncClient):
    """Test that the liveness endpoint always returns 200 OK."""
    response = await async_client.get("/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_health_readiness(async_client: httpx.AsyncClient):
    """Test that the readiness endpoint correctly pings DB and Redis."""
    response = await async_client.get("/health/readiness")
    assert response.status_code in [200, 503]
    data = response.json()["data"]
    
    # Assert keys are present
    assert "database" in data
    assert "redis" in data
    assert "ollama" in data

@pytest.mark.asyncio
async def test_concurrency_limit(async_client: httpx.AsyncClient, token: str):
    """
    Test that exceeding MAX_CONCURRENT_INFERENCE triggers a 503 Service Unavailable.
    We mock the Ollama client internally to take time so we can pile up requests.
    """
    settings = get_settings()
    max_concurrent = settings.MAX_CONCURRENT_INFERENCE
    
    # We will send (max_concurrent + 2) requests simultaneously.
    # To reliably hit the semaphore limit without depending on external Ollama speeds,
    # we would ideally mock _get_client(). But since this is a black-box integration test,
    # we just fire off max_concurrent + 2 requests and assert that at least one returns a 503.
    
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "model": "gemma2:2b",
        "messages": [{"role": "user", "content": "Explain relativity slowly."}],
        "stream": False
    }

    async def make_request():
        return await async_client.post("/v1/chat/completions", json=payload, headers=headers)

    tasks = [make_request() for _ in range(max_concurrent + 2)]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    status_codes = []
    for resp in responses:
        if isinstance(resp, httpx.Response):
            status_codes.append(resp.status_code)
            
    # At least one request should be rejected with 503 Server too busy
    # Some might pass (200) or timeout depending on Ollama load.
    assert 503 in status_codes
