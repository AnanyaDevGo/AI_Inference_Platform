from __future__ import annotations

import structlog
import redis.asyncio as redis

from app.config import get_settings

logger = structlog.get_logger(__name__)

# Lua script for atomic token-bucket rate limiting
# Keys: [rate_limit_key]
# Args: [max_tokens, refill_rate_per_second, now_seconds]
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = max_tokens
    last_refill = now
end

-- Refill tokens based on elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 120)
    return {1, 0}
else
    -- Calculate retry_after
    local needed = 1 - tokens
    local retry_after = math.ceil(needed / refill_rate)
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 120)
    return {0, retry_after}
end
"""

_redis_pool: redis.Redis | None = None
_lua_sha: str | None = None


async def _get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _redis_pool


async def _ensure_script(r: redis.Redis) -> str:
    global _lua_sha
    if _lua_sha is None:
        _lua_sha = await r.script_load(TOKEN_BUCKET_LUA)
    return _lua_sha


async def check_rate_limit(
    org_id: str, rpm: int, burst: int
) -> tuple[bool, int]:
    """
    Token-bucket rate limiter.

    Args:
        org_id: org identifier for scoping
        rpm: requests per minute
        burst: burst capacity

    Returns:
        (allowed, retry_after_seconds)
    """
    settings = get_settings()
    try:
        r = await _get_redis()
        sha = await _ensure_script(r)

        import time
        now = int(time.time())

        # max_tokens = burst, refill_rate = rpm / 60 per second
        refill_rate = rpm / 60.0

        result = await r.evalsha(
            sha,
            1,
            f"rl:{org_id}",
            str(burst),
            str(refill_rate),
            str(now),
        )

        allowed = int(result[0]) == 1
        retry_after = int(result[1])
        return allowed, retry_after

    except Exception:
        # Redis failure — fail-open or fail-closed based on config
        if settings.RATE_LIMIT_FAIL_OPEN:
            logger.warning("rate_limit_redis_error_fail_open", org_id=org_id)
            return True, 0
        else:
            logger.error("rate_limit_redis_error_fail_closed", org_id=org_id)
            return False, 60
