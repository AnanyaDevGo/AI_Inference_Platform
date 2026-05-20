from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async test client bound to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint_returns_json(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "success" in body
    assert "data" in body
    assert "status" in body["data"]
    assert "version" in body["data"]


@pytest.mark.asyncio
async def test_health_includes_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_metrics_endpoint_accessible(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "inference_requests_total" in response.text


@pytest.mark.asyncio
async def test_chat_completion_invalid_request(client: AsyncClient) -> None:
    """Empty messages array should return 422."""
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "llama3:8b-q4_K_M", "messages": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_completion_missing_model(client: AsyncClient) -> None:
    """Missing model field should return 422."""
    response = await client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_completion_nonstreaming(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Non-streaming completion returns OpenAI-compatible JSON.
    Mocks inference_service.complete to avoid requiring live Ollama.
    """
    from app.schemas.inference import ChatCompletionResponse
    import app.routers.inference as inference_router

    mock_response = ChatCompletionResponse(
        id="chatcmpl-test",
        created=1715590800,
        model="llama3:8b-q4_K_M",
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    )

    async def mock_complete(req, org_id="anonymous"):  # noqa: ANN001
        return mock_response

    monkeypatch.setattr(inference_router.inference_service, "complete", mock_complete)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "llama3:8b-q4_K_M",
            "messages": [{"role": "user", "content": "Say hello"}],
            "stream": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "chatcmpl-test"
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "Hello!"
    assert body["usage"]["total_tokens"] == 8


@pytest.mark.asyncio
async def test_chat_completion_streaming_returns_sse(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Streaming response must have content-type text/event-stream."""
    import app.routers.inference as inference_router

    async def mock_stream(req, org_id="anonymous"):  # noqa: ANN001
        yield 'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1715590800,"model":"llama3:8b-q4_K_M","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        inference_router.inference_service, "stream_complete", mock_stream
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "llama3:8b-q4_K_M",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "data:" in response.text
    assert "[DONE]" in response.text


@pytest.mark.asyncio
async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/v1/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_error_response_never_exposes_traceback(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Error responses must never contain stack trace keywords."""
    import app.routers.inference as inference_router
    from app.utils.errors import InferenceUnavailableError

    async def mock_fail(req, org_id="anonymous"):  # noqa: ANN001
        raise InferenceUnavailableError("Cannot connect")

    monkeypatch.setattr(inference_router.inference_service, "complete", mock_fail)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "llama3:8b-q4_K_M",
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        },
    )
    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert "traceback" not in response.text.lower()
    assert "Traceback" not in response.text
    assert body["error"]["code"] == "inference_unavailable"
    assert "request_id" in body["error"]
