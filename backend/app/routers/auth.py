from __future__ import annotations

import structlog
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, Cookie
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserProfileResponse,
    GoogleAuthRequest,
    SendOtpRequest,
    VerifyOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SetupPasswordRequest,
)
from app.services.auth_service import (
    authenticate_user,
    count_users,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_or_create_default_org,
    get_or_create_custom_org,
    get_user_by_email,
    hash_password,
    store_active_refresh_token,
    revoke_refresh_token,
    is_refresh_token_valid,
    revoke_all_user_refresh_tokens,
)
from app.services.otp_service import (
    store_otp,
    verify_otp,
    get_redis_client,
    store_password_reset_otp,
    verify_password_reset_otp,
)
from app.services.email_service import send_otp_verification_email
from app.dependencies.auth import get_current_user, CurrentUser
from app.utils.errors import ValidationError, UnauthorizedError

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Google Authentication Library Import Fallback
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


@router.get("/config")
async def get_auth_config():
    """
    Exposes public auth configurations (like Google Client ID) to the frontend.
    """
    from app.config import get_settings
    settings = get_settings()
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID
    }


async def verify_google_id_token(token: str) -> dict:
    """
    Verify the Google ID token.
    Supports:
    1. Developer simulator check (mock-google-token- or google-id-).
    2. Real Google Identity verification via direct Google Tokeninfo API over HTTP (using httpx).
    3. Real Google Identity verification via local google-auth library.
    """
    from app.config import get_settings
    settings = get_settings()

    # 1. Developer Simulator Prefix Check
    if token.startswith("google-id-") or token.startswith("mock-google-token-"):
        email = token.replace("mock-google-token-", "").replace("google-id-", "")
        if "@" not in email:
            email = f"{email}@gmail.com"
        return {
            "email": email,
            "name": email.split("@")[0].capitalize(),
            "picture": f"https://api.dicebear.com/7.x/adventurer/svg?seed={email}",
            "sub": f"google-sub-{email}",
        }

    # 2. Production Google Verification - Tokeninfo API over HTTP
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
            if res.status_code == 200:
                idinfo = res.json()
                if idinfo.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
                    raise ValidationError("Invalid token issuer.")
                # Verify audience if client ID is set
                if settings.GOOGLE_CLIENT_ID and idinfo.get("aud") != settings.GOOGLE_CLIENT_ID:
                    raise ValidationError("Token audience mismatch.")
                return {
                    "email": idinfo["email"],
                    "name": idinfo.get("name", idinfo["email"].split("@")[0].capitalize()),
                    "picture": idinfo.get("picture"),
                    "sub": idinfo["sub"],
                }
    except ValidationError as ve:
        raise ve
    except Exception as e:
        logger.warning("google_tokeninfo_verification_failed", error=str(e))

    # 3. Production Google Verification - Local google-auth library fallback
    if GOOGLE_AUTH_AVAILABLE:
        try:
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=settings.GOOGLE_CLIENT_ID
            )
            return {
                "email": idinfo["email"],
                "name": idinfo.get("name", idinfo["email"].split("@")[0].capitalize()),
                "picture": idinfo.get("picture"),
                "sub": idinfo["sub"],
            }
        except Exception as e:
            logger.warning("google_library_verification_failed", error=str(e))
            raise ValidationError("Invalid Google Identity token signature.")

    raise ValidationError("Google ID token verification failed (unreachable/invalid).")


def set_refresh_cookie(response: Response, refresh_token: str):
    """Securely set the refresh token inside a secure, httpOnly cookie."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",  # CSRF-safe setting
        path="/auth",
        max_age=604800,  # 7 days
    )


# ── Custom Authentication Endpoints ──────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    existing = await get_user_by_email(db, req.email)
    if existing:
        raise ValidationError("An account with this email already exists")

    is_new = False
    if req.org_name:
        org, is_new = await get_or_create_custom_org(db, req.org_name)
    else:
        org = await get_or_create_default_org(db)

    total = await count_users(db)
    role = "platform_admin" if total == 0 else ("org_admin" if is_new else "viewer")

    user = User(
        org_id=org.id,
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=role,
        auth_provider="local",
        is_active=True,
        is_verified=True,
        password_set=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Issue Tokens
    access_token = create_access_token(user)
    refresh_token, jti = create_refresh_token(user)
    await store_active_refresh_token(str(user.id), jti, 604800)
    set_refresh_cookie(response, refresh_token)

    logger.info("user_registered", email=req.email, role=role, org=org.slug)

    return TokenResponse(
        access_token=access_token,
        user_name=user.name,
        user_email=user.email,
        requires_otp=False,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await authenticate_user(db, req.email, req.password)
    
    # Check verification status
    if not user.is_verified:
        raise ValidationError("This account is not verified. Please verify using Google sign-in.")

    # Update last login time
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Issue Tokens
    access_token = create_access_token(user)
    refresh_token, jti = create_refresh_token(user)
    await store_active_refresh_token(str(user.id), jti, 604800)
    set_refresh_cookie(response, refresh_token)

    logger.info("user_login", email=req.email)

    return TokenResponse(
        access_token=access_token,
        user_name=user.name,
        user_email=user.email,
        requires_otp=False,
    )


# ── Production-Grade Google OAuth Endpoints ──────────────────────────────────

@router.post("/google", response_model=TokenResponse)
async def google_auth(
    req: GoogleAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate/Sign Up a user via Google OAuth ID token.
    Immediately creates a user record in the DB if not existing, marked as unverified.
    """
    idinfo = await verify_google_id_token(req.id_token)
    email = idinfo["email"]
    name = idinfo["name"]
    picture = idinfo["picture"]
    google_id = idinfo["sub"]

    user = await get_user_by_email(db, email)
    if user:
        if not user.is_verified:
            # User exists in DB but is not verified. Resend OTP.
            code = await store_otp(email=email, name=user.name)
            
            from app.services.auth_service import create_verification_token
            token_payload = {
                "email": email,
                "name": user.name,
                "google_id": google_id,
                "purpose": "google_registration"
            }
            verification_token = create_verification_token(token_payload)
            await send_otp_verification_email(email, code)
            
            logger.info("google_user_exists_unverified_otp_resent", email=email)
            return TokenResponse(
                access_token="",
                user_name=user.name,
                user_email=user.email,
                requires_otp=True,
                verification_token=verification_token,
            )

        # Existing verified user -> Link Google ID if missing, or login directly
        if not user.google_id:
            user.google_id = google_id
            user.auth_provider = "google"
        
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()

        access_token = create_access_token(user)
        refresh_token, jti = create_refresh_token(user)
        await store_active_refresh_token(str(user.id), jti, 604800)
        set_refresh_cookie(response, refresh_token)

        logger.info("google_user_login_direct", email=email)
        return TokenResponse(
            access_token=access_token,
            user_name=user.name,
            user_email=user.email,
            requires_otp=False,
        )

    # First-time Registration -> Create Org & DB user immediately as unverified
    is_new = False
    if req.org_name:
        org, is_new = await get_or_create_custom_org(db, req.org_name)
    else:
        org = await get_or_create_default_org(db)

    total = await count_users(db)
    role = "platform_admin" if total == 0 else ("org_admin" if is_new else "viewer")

    user = User(
        org_id=org.id,
        name=name,
        email=email,
        password_hash=None,
        google_id=google_id,
        profile_picture=picture,
        auth_provider="google",
        role=role,
        is_active=True,
        is_verified=False,
        password_set=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    code = await store_otp(email=email, name=name)

    from app.services.auth_service import create_verification_token
    token_payload = {
        "email": email,
        "name": name,
        "google_id": google_id,
        "purpose": "google_registration"
    }
    verification_token = create_verification_token(token_payload)

    await send_otp_verification_email(email, code)
    logger.info("google_register_db_record_created_otp_dispatched", email=email)

    return TokenResponse(
        access_token="",
        user_name=name,
        user_email=email,
        requires_otp=True,
        verification_token=verification_token,
    )


@router.post("/send-otp")
async def send_otp(
    req: SendOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Resends the 6-digit OTP verification code to the email.
    """
    user = await get_user_by_email(db, req.email)
    if not user:
        raise ValidationError("No pending registration found for this email.")
        
    if user.is_verified:
        raise ValidationError("This account is already verified.")

    code = await store_otp(email=req.email, name=user.name)
    await send_otp_verification_email(req.email, code)
    logger.info("otp_resend_triggered", email=req.email)
    return {"success": True, "message": "Verification code resent successfully."}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(
    req: VerifyOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Verifies 6-digit OTP, marks user verified in DB, and returns tokens.
    """
    user = await get_user_by_email(db, req.email)
    if not user:
        raise ValidationError("User not found.")

    payload = None
    if req.verification_token:
        from app.services.auth_service import decode_token
        try:
            payload = decode_token(req.verification_token)
            if payload.get("purpose") != "google_registration":
                raise ValidationError("Invalid verification token purpose")
            if payload.get("email") != req.email:
                raise ValidationError("Verification token email mismatch")
        except Exception as e:
            raise ValidationError(f"Invalid or expired verification token: {str(e)}")
    else:
        if not req.code:
            raise ValidationError("Verification code or token is required.")
        try:
            payload = await verify_otp(req.email, req.code)
        except ValueError as e:
            raise ValidationError(str(e))
            
        if not payload:
            raise ValidationError("Invalid or expired verification code.")

    # Mark user as verified
    user.is_verified = True
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Issue Tokens
    access_token = create_access_token(user)
    refresh_token, jti = create_refresh_token(user)
    await store_active_refresh_token(str(user.id), jti, 604800)
    set_refresh_cookie(response, refresh_token)

    logger.info("google_otp_user_verified", email=user.email)

    return TokenResponse(
        access_token=access_token,
        user_name=user.name,
        user_email=user.email,
        requires_otp=False,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange refresh token cookie for a new access token and rotate the refresh cookie.
    """
    if not refresh_token:
        raise UnauthorizedError("Missing refresh token cookie.")

    payload = decode_token(refresh_token)
    user_id = payload.get("sub")
    jti = payload.get("jti")
    token_type = payload.get("type")

    if not user_id or not jti or token_type != "refresh":
        raise UnauthorizedError("Invalid refresh token payload.")

    # 1. Enforce Rotation validation via Redis
    valid = await is_refresh_token_valid(user_id, jti)
    if not valid:
        # Potential reuse attack detected! Revoke all tokens for this user
        await revoke_all_user_refresh_tokens(user_id)
        response.delete_cookie("refresh_token", path="/auth")
        logger.error("refresh_token_reuse_attack_detected", user_id=user_id, jti=jti)
        raise UnauthorizedError("Security Alert: Token already used or revoked. All active sessions terminated.")

    # Revoke old refresh token
    await revoke_refresh_token(user_id, jti)

    # Fetch user
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("Account is suspended or invalid.")

    # Issue new access + rotated refresh tokens
    access_token = create_access_token(user)
    new_refresh_token, new_jti = create_refresh_token(user)
    await store_active_refresh_token(str(user.id), new_jti, 604800)
    set_refresh_cookie(response, new_refresh_token)

    logger.info("token_rotated_successfully", user_id=user_id)

    return TokenResponse(
        access_token=access_token,
        user_name=user.name,
        user_email=user.email,
        requires_otp=False,
    )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
) -> dict:
    """
    Log out user: Revokes refresh token in Redis and clears cookie.
    """
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            user_id = payload.get("sub")
            jti = payload.get("jti")
            if user_id and jti:
                await revoke_refresh_token(user_id, jti)
        except Exception:
            pass

    response.delete_cookie("refresh_token", path="/auth")
    logger.info("user_logged_out")
    return {"success": True, "message": "Logged out successfully."}


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Return authenticated user profile data.
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(current_user.user_id)))
    user = result.scalar_one()

    # Get org name
    from app.models.org import Org
    org_result = await db.execute(select(Org).where(Org.id == user.org_id))
    org = org_result.scalar_one()

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        profile_picture=user.profile_picture,
        role=user.role,
        org_id=str(user.org_id),
        org_name=org.name,
        is_active=user.is_active,
    )


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Request a password reset OTP.
    Secured against user enumeration attacks.
    """
    user = await get_user_by_email(db, req.email)
    
    # Check if we should trigger actual reset flow
    should_send = user is not None and user.is_verified

    if should_send:
        code = await store_password_reset_otp(req.email)
        
        # Send the code using pluggable provider registry
        from app.services.email_service import get_email_provider
        provider = get_email_provider()
        
        subject = "Reset your InferVoyage Password"
        body_text = f"Your 6-digit password reset verification code is: {code}\n\nThis code expires in 5 minutes."
        body_html = f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #4f46e5; text-align: center;">InferVoyage</h2>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
            <p>Hello,</p>
            <p>We received a request to reset your password. Please enter the following 6-digit verification code to proceed:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 2.2rem; font-weight: 700; letter-spacing: 8px; background-color: #f3f4f6; padding: 12px 24px; border-radius: 6px; color: #1f2937; border: 1px solid #e5e7eb;">
                    {code}
                </span>
            </div>
            <p style="color: #6b7280; font-size: 0.875rem;">This code is valid for <strong>5 minutes</strong>. If you did not request a password reset, you can safely ignore this email.</p>
        </div>
        """
        
        await provider.send_email(
            to_email=req.email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        logger.info("forgot_password_otp_dispatched", email=req.email)

    # Always generate a valid-looking reset token to prevent enumeration response delta
    from app.services.auth_service import create_reset_token
    reset_token = create_reset_token(req.email)

    return {
        "success": True,
        "message": "If an account exists for this email, a reset link has been sent.",
        "reset_token": reset_token,
    }


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reset password with verified OTP and reset token.
    """
    if not req.reset_token:
        raise ValidationError("Reset token is required.")

    from app.services.auth_service import decode_token
    try:
        payload = decode_token(req.reset_token)
        if payload.get("purpose") != "password_reset":
            raise ValidationError("Invalid reset token purpose")
        if payload.get("email") != req.email:
            raise ValidationError("Reset token email mismatch")
    except Exception as e:
        raise ValidationError(f"Invalid or expired reset token: {str(e)}")

    user = await get_user_by_email(db, req.email)
    should_verify = user is not None and user.is_verified

    if should_verify:
        if not req.code:
            raise ValidationError("Verification code is required.")
        try:
            verified = await verify_password_reset_otp(req.email, req.code)
        except ValueError as e:
            raise ValidationError(str(e))
        if not verified:
            raise ValidationError("Invalid or expired verification code.")
    else:
        # Silently succeed to prevent user enumeration
        logger.info("password_reset_ignored_user_not_found_or_google_only", email=req.email)
        return {"success": True, "message": "Password reset successfully!"}

    user.password_hash = hash_password(req.new_password)
    user.password_set = True
    await db.flush()

    logger.info("password_reset_successful", email=req.email)
    return {"success": True, "message": "Password reset successfully!"}


@router.post("/setup-password")
async def setup_password(
    req: SetupPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Setup password for Google-created users who want to set a password later.
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(current_user.user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise ValidationError("User not found.")

    user.password_hash = hash_password(req.password)
    user.password_set = True
    await db.flush()

    logger.info("user_password_setup_completed", email=user.email)
    return {"success": True, "message": "Password setup completed successfully."}


