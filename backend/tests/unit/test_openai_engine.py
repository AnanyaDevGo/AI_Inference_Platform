from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from app.schemas.inference import ChatCompletionRequest, ChatMessage
from app.services.inference_service import complete, stream_complete, check_ollama_health, list_ollama_models

@pytest.fixture
def mock_settings():
    with patch("app.services.inference_service.get_settings") as mock:
        settings = MagicMock()
        settings.INFERENCE_ENGINE = "openai_compatible"
        settings.INFERENCE_ENGINE_URL = "http://mock-openai-engine"
        settings.INFERENCE_TIMEOUT_SECONDS = 10
        settings.INFERENCE_NUM_CTX = 2048
        settings.MAX_CONCURRENT_INFERENCE = 4
        settings.OLLAMA_BASE_URL = "http://localhost:11434"
        mock.return_value = settings
        yield settings

@pytest.mark.asyncio
async def test_openai_compatible_complete(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "chatcmpl-mock",
        "created": 123456789,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from mock OpenAI!"},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        }
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    req = ChatCompletionRequest(
        model="gpt-4",
        messages=[ChatMessage(role="user", content="hello")],
        stream=False
    )

    with patch("app.services.inference_service._get_client", return_value=mock_client):
        res = await complete(req)
        
        assert res.id == "chatcmpl-mock"
        assert res.choices[0].message.content == "Hello from mock OpenAI!"
        assert res.usage.prompt_tokens == 10
        assert res.usage.completion_tokens == 15
        mock_client.post.assert_called_once_with("/v1/chat/completions", json=req.model_dump())

@pytest.mark.asyncio
async def test_openai_compatible_stream_complete(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    async def mock_aiter_lines():
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}"
        yield "data: {\"choices\": [{\"delta\": {\"content\": \" world\"}}]}"
        yield "data: [DONE]"
        
    mock_response.aiter_lines = mock_aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)

    req = ChatCompletionRequest(
        model="gpt-4",
        messages=[ChatMessage(role="user", content="hello")],
        stream=True
    )

    with patch("app.services.inference_service._get_client", return_value=mock_client):
        chunks = []
        async for chunk in stream_complete(req):
            chunks.append(chunk)
            
        assert len(chunks) == 3 # 2 data chunks + 1 final DONE sentinel
        assert "Hello" in chunks[0]
        assert "world" in chunks[1]
        assert "[DONE]" in chunks[2]

@pytest.mark.asyncio
async def test_openai_compatible_health_and_models(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "model-a"},
            {"id": "model-b"}
        ]
    }
    
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)
    
    with patch("app.services.inference_service._get_client", return_value=mock_client):
        health = await check_ollama_health()
        assert health is True
        mock_client.get.assert_called_with("/v1/models", timeout=5.0)
        
        models = await list_ollama_models()
        assert len(models) == 2
        assert models[0]["name"] == "model-a"
        assert models[1]["name"] == "model-b"
