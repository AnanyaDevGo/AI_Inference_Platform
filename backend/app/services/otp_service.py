from __future__ import annotations

import hashlib
import secrets
import structlog
import redis.asyncio as redis
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.otp import Otp
from app.utils.errors import ValidationError

logger = structlog.get_logger(__name__)

_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """Retrieve or initialize the async Redis client (used for token rotation)."""
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
    db: AsyncSession,
    email: str,
    purpose: str,
) -> str:
    """
    Generate an OTP code, save the metadata securely in Postgres,
    and return the plain code.strictly expires in 5 minutes (300 seconds).
    Enforces maximum of 3 resends / requests within 15 minutes.
    """
    email_clean = email.strip().lower()
    
    # 1. Rate limit check (Max 3 OTP requests within 15 minutes)
    fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    stmt = select(Otp).where(
        Otp.email == email_clean,
        Otp.purpose == purpose,
        Otp.created_at >= fifteen_minutes_ago
    )
    res = await db.execute(stmt)
    existing_otps = res.scalars().all()
    if len(existing_otps) >= 3:
        logger.warning("otp_request_rate_limited", email=email_clean, purpose=purpose)
        raise ValidationError("Too many requests. Please wait before trying again.")

    # 2. Generate and store
    code = generate_otp_code()
    code_hash = hash_otp_code(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    otp_record = Otp(
        email=email_clean,
        otp_hash=code_hash,
        purpose=purpose,
        expires_at=expires_at,
        attempts=0,
        verified=False,
    )
    db.add(otp_record)
    await db.flush()
    
    logger.info("otp_stored_in_db", email=email_clean, purpose=purpose, expires_at=expires_at)
    return code


async def verify_otp(
    db: AsyncSession,
    email: str,
    purpose: str,
    code: str,
) -> bool:
    """
    Verify the given OTP code for the email & purpose:
    - Checks attempts rate-limiting (max 5 incorrect tries).
    - Checks code match.
    - If valid, marks verified in DB and returns True.
    """
    email_clean = email.strip().lower()
    
    # Get latest OTP for this email and purpose
    stmt = (
        select(Otp)
        .where(Otp.email == email_clean, Otp.purpose == purpose)
        .order_by(Otp.created_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    otp_record = res.scalar_one_or_none()
    
    if not otp_record:
        logger.warning("otp_verification_failed_not_found", email=email_clean, purpose=purpose)
        raise ValidationError("Invalid verification code.")
        
    # 1. Enforce lockout (Max 5 attempts)
    if otp_record.attempts >= 5:
        logger.warning("otp_lockout_attempts_exceeded", email=email_clean, purpose=purpose)
        raise ValidationError("Maximum verification attempts exceeded. Please request a new code.")
        
    if otp_record.verified:
        logger.warning("otp_already_verified_re-use_attempt", email=email_clean, purpose=purpose)
        raise ValidationError("This code has already been verified. Please request a new code.")

    # Increment attempt counter
    otp_record.attempts += 1
    await db.flush()

    if otp_record.attempts > 5:
        await db.commit()
        raise ValidationError("Maximum verification attempts exceeded. Please request a new code.")

    # 2. Check expiry
    if datetime.now(timezone.utc) > otp_record.expires_at:
        logger.warning("otp_verification_failed_expired", email=email_clean, purpose=purpose)
        await db.commit()
        raise ValidationError("The verification code has expired. Please request a new code.")

    # 3. Check match
    input_hash = hash_otp_code(code)
    if otp_record.otp_hash != input_hash:
        logger.warning("otp_verification_failed_incorrect_code", email=email_clean, purpose=purpose, attempts=otp_record.attempts)
        if otp_record.attempts >= 5:
            await db.commit()
            raise ValidationError("Maximum verification attempts exceeded. Please request a new code.")
        await db.commit()
        raise ValidationError("Invalid verification code.")
        
    # 4. Successful match -> mark verified and return True
    otp_record.verified = True
    await db.flush()
    logger.info("otp_verification_succeeded", email=email_clean, purpose=purpose)
    return True


async def cleanup_expired_otps(db: AsyncSession) -> None:
    """Delete all expired OTPs from the database."""
    stmt = delete(Otp).where(Otp.expires_at < datetime.now(timezone.utc))
    await db.execute(stmt)
    await db.flush()
    logger.info("expired_otps_cleaned_up")
