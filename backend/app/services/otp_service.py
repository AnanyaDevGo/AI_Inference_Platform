from __future__ import annotations

import hashlib
import json
import secrets
import structlog
import redis.asyncio as redis
from typing import Any

from app.config import get_settings

logger = structlog.get_logger(__name__)

_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """Retrieve or initialize the async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _redis_client


def generate_otp_code() -> str:
    """Generate a cryptographically secure 6-digit numeric OTP."""
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


def hash_otp_code(code: str) -> str:
    """Hash the OTP code using SHA-256 for secure comparison."""
    return hashlib.sha256(code.strip().encode()).hexdigest()


async def store_otp(
    email: str,
    name: str | None = None,
    org_name: str | None = None,
    google_id: str | None = None,
    profile_picture: str | None = None,
) -> str:
    """
    Generate an OTP code, save the metadata securely in Redis under email,
    and return the plain code. Strictly expires in 5 minutes (300 seconds).
    """
    code = generate_otp_code()
    code_hash = hash_otp_code(code)
    
    payload = {
        "code_hash": code_hash,
        "name": name,
        "org_name": org_name,
        "google_id": google_id,
        "profile_picture": profile_picture,
        "attempts": 0,
    }
    
    r = await get_redis_client()
    key = f"otp:{email.strip().lower()}"
    
    # Store payload as stringified JSON with 300 seconds (5 minutes) expiry
    await r.setex(key, 300, json.dumps(payload))
    
    logger.info("otp_stored_in_redis", email=email, expires_in=300)
    return code


async def verify_otp(email: str, code: str) -> dict[str, Any] | None:
    """
    Verify the given OTP code for the email:
    - Checks attempts rate-limiting (max 5 incorrect tries).
    - Checks code match.
    - If valid, returns the associated metadata payload and deletes the key.
    """
    r = await get_redis_client()
    email_key = email.strip().lower()
    key = f"otp:{email_key}"
    
    data_str = await r.get(key)
    if not data_str:
        logger.warning("otp_verification_failed_not_found_or_expired", email=email)
        return None
        
    payload = json.loads(data_str)
    
    # 1. Enforce rate limiting of verification attempts (Max 5 attempts)
    if payload.get("attempts", 0) >= 5:
        logger.warning("otp_verification_failed_max_attempts_exceeded", email=email)
        await r.delete(key)
        raise ValueError("Too many failed attempts. Please request a new verification code.")
        
    # 2. Check match
    input_hash = hash_otp_code(code)
    if payload["code_hash"] != input_hash:
        # Increment attempt counter
        payload["attempts"] = payload.get("attempts", 0) + 1
        await r.setex(key, 300, json.dumps(payload))
        logger.warning("otp_verification_failed_incorrect_code", email=email, attempts=payload["attempts"])
        return None
        
    # 3. Successful match -> clear code from Redis and return original user metadata
    await r.delete(key)
    logger.info("otp_verification_succeeded", email=email)
    return payload


async def store_password_reset_otp(email: str) -> str:
    """
    Generate an OTP for password reset, save it in Redis, and return the plain code.
    Expires in 300 seconds (5 minutes).
    """
    code = generate_otp_code()
    code_hash = hash_otp_code(code)
    
    payload = {
        "code_hash": code_hash,
        "attempts": 0,
    }
    
    r = await get_redis_client()
    key = f"reset_otp:{email.strip().lower()}"
    await r.setex(key, 300, json.dumps(payload))
    
    logger.info("reset_otp_stored_in_redis", email=email, expires_in=300)
    return code


async def verify_password_reset_otp(email: str, code: str) -> bool:
    """
    Verify the reset password OTP. Returns True if verified, False/raises otherwise.
    """
    r = await get_redis_client()
    email_key = email.strip().lower()
    key = f"reset_otp:{email_key}"
    
    data_str = await r.get(key)
    if not data_str:
        logger.warning("reset_otp_verification_failed_not_found_or_expired", email=email)
        return False
        
    payload = json.loads(data_str)
    
    # Enforce attempts limit
    if payload.get("attempts", 0) >= 5:
        logger.warning("reset_otp_max_attempts_exceeded", email=email)
        await r.delete(key)
        raise ValueError("Too many failed attempts. Please request a new reset code.")
        
    input_hash = hash_otp_code(code)
    if payload["code_hash"] != input_hash:
        payload["attempts"] = payload.get("attempts", 0) + 1
        await r.setex(key, 300, json.dumps(payload))
        logger.warning("reset_otp_incorrect_code", email=email, attempts=payload["attempts"])
        return False
        
    # Valid code -> delete from Redis
    await r.delete(key)
    logger.info("reset_otp_verification_succeeded", email=email)
    return True

