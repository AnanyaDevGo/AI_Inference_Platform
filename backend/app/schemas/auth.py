from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    org_name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    user_email: str
    requires_otp: bool = False
    verification_token: str | None = None


class UserProfileResponse(BaseModel):
    id: str
    email: str
    name: str
    profile_picture: str | None = None
    role: str
    org_id: str
    org_name: str
    is_active: bool


class GoogleAuthRequest(BaseModel):
    id_token: str
    org_name: str | None = Field(default=None, max_length=100)


class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str | None = Field(default=None, min_length=6, max_length=6)
    verification_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str | None = Field(default=None, min_length=6, max_length=6)
    reset_token: str | None = None
    new_password: str = Field(..., min_length=8, max_length=128)


class SetupPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


