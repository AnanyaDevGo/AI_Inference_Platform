from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_session_factory
from app.dependencies.auth import CurrentUser, get_current_user_or_api_key
from app.models.org import Org
from app.schemas.inference import ChatCompletionRequest, ChatCompletionResponse
from app.services import inference_service
from app.services.rate_limit_service import check_rate_limit
from app.services.usage_service import log_usage
from app.utils.errors import RateLimitError
from sqlalchemy import select

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["inference"])


async def _get_org_limits(db: AsyncSession, org_id: str) -> tuple[int, int]:
    """Fetch org rate limits from DB."""
    try:
        result = await db.execute(
            select(Org.rate_limit_rpm, Org.rate_limit_burst)
            .where(Org.id == uuid.UUID(org_id))
        )
        row = result.one_or_none()
        if row:
            return row.rate_limit_rpm, row.rate_limit_burst
    except Exception as e:
        logger.exception("get_org_limits_failed", org_id=org_id, error=str(e))
    return 60, 10  # defaults


@router.post(
    "/chat/completions",
    summary="Create chat completion",
    description="OpenAI-compatible chat completion endpoint. Requires JWT or API key.",
    response_model=ChatCompletionResponse,
)
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | ChatCompletionResponse:
    """
    Route chat completion requests to Ollama.
    Protected by JWT or API key. Rate-limited per org.
    """
    org_id = current_user.org_id

    # ── Rate limit check ──
    rpm, burst = await _get_org_limits(db, org_id)
    allowed, retry_after = await check_rate_limit(org_id, rpm, burst)
    if not allowed:
        await db.rollback()
        await db.close()
        raise RateLimitError(retry_after=retry_after)

    # Release the database session/connection back to the pool immediately
    # before we start the slow inference call.
    await db.rollback()
    await db.close()

    if request.stream:
        request_id = response.headers.get("X-Request-ID", str(uuid.uuid4()))
        # Capture values needed after the stream (session is closed by then)
        _org_id = org_id
        _user_id = current_user.user_id
        _api_key_id = current_user.api_key_id
        _model = request.model
        _request_id = request_id

        async def on_complete_callback(prompt_tokens: int, completion_tokens: int) -> None:
            """Open a fresh session — shielded from CancelledError on client disconnect."""
            async def _do_log():
                factory = get_session_factory()
                async with factory() as fresh_db:
                    try:
                        await log_usage(
                            fresh_db,
                            org_id=_org_id,
                            user_id=_user_id,
                            api_key_id=_api_key_id,
                            model_name=_model,
                            request_id=_request_id,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            duration_ms=0,
                            status="success" if (prompt_tokens > 0 or completion_tokens > 0) else "cancelled",
                        )
                        await fresh_db.commit()
                    except Exception:
                        logger.exception("stream_usage_log_failed", model=_model, org_id=_org_id)

            try:
                await asyncio.shield(asyncio.ensure_future(_do_log()))
            except asyncio.CancelledError:
                # Shield ensures _do_log() continues even when we're cancelled
                pass

        return StreamingResponse(
            inference_service.stream_complete(request, org_id=org_id, on_complete=on_complete_callback),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await inference_service.complete(request, org_id=org_id)
    # Log usage for non-streaming requests using a fresh DB session
    request_id = response.headers.get("X-Request-ID", str(uuid.uuid4()))
    factory = get_session_factory()
    async with factory() as fresh_db:
        try:
            await log_usage(
                fresh_db,
                org_id=org_id,
                user_id=current_user.user_id,
                api_key_id=current_user.api_key_id,
                model_name=request.model,
                request_id=request_id,
                prompt_tokens=result.usage.prompt_tokens if result.usage else 0,
                completion_tokens=result.usage.completion_tokens if result.usage else 0,
                duration_ms=0,
                status="success",
            )
            await fresh_db.commit()
        except Exception:
            logger.exception("completions_usage_log_failed", model=request.model, org_id=org_id)
    return result


@router.get("/models")
async def list_models(
    current_user: CurrentUser = Depends(get_current_user_or_api_key),
):
    """
    List available models from Ollama.
    """
    models = await inference_service.list_ollama_models()
    return {"models": [m.get("name") for m in models]}
