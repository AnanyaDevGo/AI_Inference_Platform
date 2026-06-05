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
async def test_concurrency_limit(
    async_client: httpx.AsyncClient, token: str, monkeypatch: pytest.MonkeyPatch
):
    """
    Test that exceeding MAX_CONCURRENT_INFERENCE triggers a 503 Service Unavailable.
    We mock the Ollama client internally to take time so we can pile up requests.
    """
    import app.services.inference_service as inference_service
    settings = get_settings()
    max_concurrent = settings.MAX_CONCURRENT_INFERENCE

    # Mock the internal httpx client to sleep for 1 second to simulate slow inference
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def post(self, url, **kwargs):
            await asyncio.sleep(1.0)
            mock_resp = httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "mocked response"},
                    "done_reason": "stop",
                    "prompt_eval_count": 5,
                    "eval_count": 5
                }
            )
            mock_resp.request = httpx.Request("POST", url)
            return mock_resp

    monkeypatch.setattr(inference_service, "_get_client", MockAsyncClient)

    import app.routers.inference as inference_router
    async def mock_check_rate_limit(*args, **kwargs):
        return True, 0
    monkeypatch.setattr(inference_router, "check_rate_limit", mock_check_rate_limit)

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
    assert 503 in status_codes
