from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Callable, Coroutine

import httpx
import structlog

from app.config import get_settings
from app.observability.metrics import (
    INFERENCE_DURATION_SECONDS,
    INFERENCE_REQUESTS_TOTAL,
    INFERENCE_TOKENS_TOTAL,
    INFERENCE_TTFT_SECONDS,
    INFERENCE_CONCURRENT_REQUESTS,
    INFERENCE_QUEUE_LENGTH,
    RESPONSE_SIZE_BYTES,
)
from app.schemas.inference import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.utils.errors import InferenceTimeoutError, InferenceUnavailableError

logger = structlog.get_logger(__name__)

# ── Ollama field mapping (OpenAI → Ollama) ───────────────────────────────────

def _build_ollama_payload(req: ChatCompletionRequest) -> dict[str, Any]:
    settings = get_settings()
    return {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "stream": req.stream,
        "options": {
            "temperature": req.temperature,
            "num_predict": req.max_tokens,
            "top_p": req.top_p,
            "num_ctx": settings.INFERENCE_NUM_CTX,
        },
    }


def _make_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


# ── HTTP client factory ──────────────────────────────────────────────────────

def _get_client() -> httpx.AsyncClient:
    settings = get_settings()
    base_url = settings.INFERENCE_ENGINE_URL if settings.INFERENCE_ENGINE == "openai_compatible" and settings.INFERENCE_ENGINE_URL else settings.OLLAMA_BASE_URL
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(
            connect=5.0,
            read=settings.INFERENCE_TIMEOUT_SECONDS,
            write=10.0,
            pool=5.0,
        ),
    )


# ── Concurrency & Lifecycle ──────────────────────────────────────────────────

from contextlib import asynccontextmanager

_inference_semaphore: asyncio.Semaphore | None = None
_active_inferences: int = 0

def _get_semaphore() -> asyncio.Semaphore:
    global _inference_semaphore
    if _inference_semaphore is None:
        settings = get_settings()
        _inference_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFERENCE)
    return _inference_semaphore

def get_active_inferences() -> int:
    return _active_inferences

@asynccontextmanager
async def _inference_slot(model: str):
    global _active_inferences
    sem = _get_semaphore()
    
    # Update queue depth
    queue_len = len(sem._waiters) if sem._waiters else 0
    INFERENCE_QUEUE_LENGTH.labels(model=model).set(queue_len)
    
    if sem.locked():
        raise InferenceUnavailableError("Server too busy: maximum concurrent inferences reached.")
    
    await sem.acquire()
    _active_inferences += 1
    INFERENCE_CONCURRENT_REQUESTS.labels(model=model).inc()
    try:
        yield
    finally:
        _active_inferences -= 1
        INFERENCE_CONCURRENT_REQUESTS.labels(model=model).dec()
        sem.release()


# ── Non-streaming inference ──────────────────────────────────────────────────

async def complete(
    req: ChatCompletionRequest,
    org_id: str = "anonymous",
) -> ChatCompletionResponse:
    """Proxy a non-streaming chat completion request to Ollama or OpenAI-compatible engine."""
    settings = get_settings()
    completion_id = _make_completion_id()
    start = time.perf_counter()

    logger.info(
        "inference_start",
        model=req.model,
        org_id=org_id,
        stream=False,
        message_count=len(req.messages),
        engine=settings.INFERENCE_ENGINE,
    )

    try:
        async with _inference_slot(req.model):
            async with _get_client() as client:
                try:
                    if settings.INFERENCE_ENGINE == "openai_compatible":
                        payload = req.model_dump()
                        response = await asyncio.wait_for(
                            client.post("/v1/chat/completions", json=payload),
                            timeout=settings.INFERENCE_TIMEOUT_SECONDS,
                        )
                    else:
                        payload = _build_ollama_payload(req)
                        response = await asyncio.wait_for(
                            client.post("/api/chat", json=payload),
                            timeout=settings.INFERENCE_TIMEOUT_SECONDS,
                        )
                except asyncio.TimeoutError:
                    _record_metrics(org_id, req.model, "timeout", 0, 0, start)
                    raise InferenceTimeoutError()
                except httpx.ConnectError:
                    _record_metrics(org_id, req.model, "error", 0, 0, start)
                    raise InferenceUnavailableError(f"Cannot connect to {settings.INFERENCE_ENGINE}")

        if response.status_code != 200:
            _record_metrics(org_id, req.model, "error", 0, 0, start)
            raise InferenceUnavailableError(
                f"Inference engine returned status {response.status_code}: {response.text}"
            )

        body = response.json()
        if settings.INFERENCE_ENGINE == "openai_compatible":
            choices_data = []
            for idx, c in enumerate(body.get("choices", [])):
                msg = c.get("message", {})
                choices_data.append({
                    "index": c.get("index", idx),
                    "message": {
                        "role": msg.get("role", "assistant"),
                        "content": msg.get("content", ""),
                    },
                    "finish_reason": c.get("finish_reason", "stop"),
                })
            usage_data = body.get("usage", {})
            prompt_tokens = usage_data.get("prompt_tokens", 0)
            completion_tokens = usage_data.get("completion_tokens", 0)

            _record_metrics(
                org_id, req.model, "success", prompt_tokens, completion_tokens, start
            )
            total_content = "".join([c["message"]["content"] for c in choices_data])
            RESPONSE_SIZE_BYTES.labels(handler="/v1/chat/completions").observe(len(total_content.encode("utf-8")))

            logger.info(
                "inference_complete",
                model=req.model,
                org_id=org_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

            return ChatCompletionResponse(
                id=body.get("id", completion_id),
                created=body.get("created", int(time.time())),
                model=body.get("model", req.model),
                choices=choices_data,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )
        else:
            content = body.get("message", {}).get("content", "")
            prompt_tokens = body.get("prompt_eval_count", 0)
            completion_tokens = body.get("eval_count", 0)

            _record_metrics(
                org_id, req.model, "success", prompt_tokens, completion_tokens, start
            )
            RESPONSE_SIZE_BYTES.labels(handler="/v1/chat/completions").observe(len(content.encode("utf-8")))

            logger.info(
                "inference_complete",
                model=req.model,
                org_id=org_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

            return ChatCompletionResponse(
                id=completion_id,
                created=int(time.time()),
                model=req.model,
                choices=[
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": body.get("done_reason", "stop"),
                    }
                ],
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )

    except (InferenceTimeoutError, InferenceUnavailableError):
        raise
    except Exception as exc:
        _record_metrics(org_id, req.model, "error", 0, 0, start)
        logger.exception("inference_unexpected_error", model=req.model, org_id=org_id)
        raise InferenceUnavailableError(str(exc)) from exc


# ── Streaming inference ──────────────────────────────────────────────────────

async def stream_complete(
    req: ChatCompletionRequest,
    org_id: str = "anonymous",
    on_complete: Callable[[int, int], Coroutine[Any, Any, None]] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Proxy a streaming chat completion to Ollama or OpenAI-compatible engine.
    Yields SSE-formatted strings: 'data: <json>\n\n'
    Measures TTFT on first non-empty chunk.
    Handles client disconnect via GeneratorExit / CancelledError.
    """
    settings = get_settings()
    completion_id = _make_completion_id()
    start = time.perf_counter()
    first_token = True
    ttft_ms: int | None = None
    prompt_tokens = 0
    completion_tokens = 0
    full_content_chunks = []

    logger.info(
        "inference_stream_start",
        model=req.model,
        org_id=org_id,
        message_count=len(req.messages),
        engine=settings.INFERENCE_ENGINE,
    )

    try:
        async with _inference_slot(req.model):
            async with _get_client() as client:
                try:
                    if settings.INFERENCE_ENGINE == "openai_compatible":
                        payload = req.model_dump()
                        async with client.stream(
                            "POST",
                            "/v1/chat/completions",
                            json=payload,
                            timeout=settings.INFERENCE_TIMEOUT_SECONDS,
                        ) as response:
                            if response.status_code != 200:
                                _record_metrics(org_id, req.model, "error", 0, 0, start)
                                raise InferenceUnavailableError(
                                    f"Inference engine returned status {response.status_code}"
                                )

                            async for line in response.aiter_lines():
                                if not line:
                                    continue

                                if line.startswith("data: "):
                                    line_content = line[6:].strip()
                                elif line.startswith("data:"):
                                    line_content = line[5:].strip()
                                else:
                                    continue

                                if line_content == "[DONE]":
                                    break

                                try:
                                    chunk_data = json.loads(line_content)
                                except json.JSONDecodeError:
                                    continue

                                choices = chunk_data.get("choices", [])
                                content = ""
                                finish_reason = None
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    finish_reason = choices[0].get("finish_reason", None)

                                if content:
                                    completion_tokens += 1
                                    full_content_chunks.append(content)

                                # Measure TTFT on first content-bearing chunk
                                if first_token and content:
                                    ttft_ms = int((time.perf_counter() - start) * 1000)
                                    first_token = False
                                    INFERENCE_TTFT_SECONDS.labels(
                                        org_id=org_id, model=req.model
                                    ).observe(ttft_ms / 1000)
                                    logger.info(
                                        "inference_stream_ttft",
                                        model=req.model,
                                        org_id=org_id,
                                        ttft_ms=ttft_ms,
                                    )

                                usage = chunk_data.get("usage", None)
                                if usage:
                                    prompt_tokens = usage.get("prompt_tokens", 0)
                                    completion_tokens = usage.get("completion_tokens", 0)

                                chunk = ChatCompletionChunk(
                                    id=chunk_data.get("id", completion_id),
                                    created=chunk_data.get("created", int(time.time())),
                                    model=chunk_data.get("model", req.model),
                                    choices=[
                                        {
                                            "index": 0,
                                            "delta": {
                                                "role": "assistant" if first_token else None,
                                                "content": content or None,
                                            },
                                            "finish_reason": finish_reason,
                                        }
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"

                    else:
                        payload = _build_ollama_payload(req)
                        async with client.stream(
                            "POST",
                            "/api/chat",
                            json=payload,
                            timeout=settings.INFERENCE_TIMEOUT_SECONDS,
                        ) as response:
                            if response.status_code != 200:
                                _record_metrics(org_id, req.model, "error", 0, 0, start)
                                raise InferenceUnavailableError(
                                    f"Ollama returned status {response.status_code}"
                                )

                            async for line in response.aiter_lines():
                                if not line:
                                    continue

                                try:
                                    chunk_data = json.loads(line)
                                except json.JSONDecodeError:
                                    continue

                                content = chunk_data.get("message", {}).get("content", "")
                                done = chunk_data.get("done", False)

                                if content:
                                    completion_tokens += 1
                                    full_content_chunks.append(content)

                                # Measure TTFT on first content-bearing chunk
                                if first_token and content:
                                    ttft_ms = int((time.perf_counter() - start) * 1000)
                                    first_token = False
                                    INFERENCE_TTFT_SECONDS.labels(
                                        org_id=org_id, model=req.model
                                    ).observe(ttft_ms / 1000)
                                    logger.info(
                                        "inference_stream_ttft",
                                        model=req.model,
                                        org_id=org_id,
                                        ttft_ms=ttft_ms,
                                    )

                                if done:
                                    prompt_tokens = chunk_data.get("prompt_eval_count", 0)
                                    completion_tokens = chunk_data.get("eval_count", 0)

                                chunk = ChatCompletionChunk(
                                    id=completion_id,
                                    created=int(time.time()),
                                    model=req.model,
                                    choices=[
                                        {
                                            "index": 0,
                                            "delta": {
                                                "role": "assistant" if first_token else None,
                                                "content": content or None,
                                            },
                                            "finish_reason": "stop" if done else None,
                                        }
                                    ],
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"

                                if done:
                                    break

                except asyncio.TimeoutError:
                    _record_metrics(org_id, req.model, "timeout", 0, 0, start)
                    raise InferenceTimeoutError()
                except httpx.ConnectError:
                    _record_metrics(org_id, req.model, "error", 0, 0, start)
                    raise InferenceUnavailableError(f"Cannot connect to {settings.INFERENCE_ENGINE}")

        # Final done sentinel
        yield "data: [DONE]\n\n"

        _record_metrics(
            org_id, req.model, "success", prompt_tokens, completion_tokens, start
        )
        full_content = "".join(full_content_chunks)
        RESPONSE_SIZE_BYTES.labels(handler="/v1/chat/completions").observe(len(full_content.encode("utf-8")))
        logger.info(
            "inference_stream_complete",
            model=req.model,
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=int((time.perf_counter() - start) * 1000),
            ttft_ms=ttft_ms,
        )
        if on_complete:
            try:
                await on_complete(prompt_tokens, completion_tokens)
            except Exception:
                logger.exception("inference_stream_callback_failed")

    except (GeneratorExit, asyncio.CancelledError):
        # Client disconnected mid-stream
        logger.info(
            "inference_stream_client_disconnect",
            model=req.model,
            org_id=org_id,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        _record_metrics(org_id, req.model, "cancelled", 0, 0, start)
        if on_complete:
            try:
                await on_complete(0, 0)
            except Exception:
                pass
        return

    except (InferenceTimeoutError, InferenceUnavailableError):
        raise

    except Exception as exc:
        logger.exception("inference_stream_error", model=req.model, org_id=org_id)
        _record_metrics(org_id, req.model, "error", 0, 0, start)
        raise InferenceUnavailableError(str(exc)) from exc


# ── Helpers ──────────────────────────────────────────────────────────────────

def _record_metrics(
    org_id: str,
    model: str,
    status: str,
    prompt_tokens: int,
    completion_tokens: int,
    start: float,
) -> None:
    duration = time.perf_counter() - start
    INFERENCE_REQUESTS_TOTAL.labels(org_id=org_id, model=model, status=status).inc()
    INFERENCE_DURATION_SECONDS.labels(org_id=org_id, model=model).observe(duration)
    if prompt_tokens:
        INFERENCE_TOKENS_TOTAL.labels(
            org_id=org_id, model=model, token_type="prompt"
        ).inc(prompt_tokens)
    if completion_tokens:
        INFERENCE_TOKENS_TOTAL.labels(
            org_id=org_id, model=model, token_type="completion"
        ).inc(completion_tokens)


# ── Ollama health check ───────────────────────────────────────────────────────

async def check_ollama_health() -> bool:
    """Returns True if inference engine is reachable. Used by /health endpoint."""
    settings = get_settings()
    try:
        async with _get_client() as client:
            if settings.INFERENCE_ENGINE == "openai_compatible":
                resp = await client.get("/v1/models", timeout=5.0)
                return resp.status_code == 200
            else:
                resp = await client.get("/api/tags", timeout=5.0)
                return resp.status_code == 200
    except Exception:
        return False


async def list_ollama_models() -> list[dict[str, Any]]:
    """Return the list of models available in the inference engine."""
    settings = get_settings()
    try:
        async with _get_client() as client:
            if settings.INFERENCE_ENGINE == "openai_compatible":
                resp = await client.get("/v1/models", timeout=5.0)
                if resp.status_code == 200:
                    models_data = resp.json().get("data", [])
                    return [{"name": m.get("id")} for m in models_data]
            else:
                resp = await client.get("/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    return resp.json().get("models", [])
    except Exception:
        pass
    return []
