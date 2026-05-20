from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application errors. Never expose stack traces to callers."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        self.message = message or self.__class__.message
        self.extra = kwargs
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
    message = "Request validation failed"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required"


class TokenExpiredError(AppError):
    status_code = 401
    code = "token_expired"
    message = "Token has expired"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "Invalid email or password"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Insufficient permissions"


class CrossOrgAccessError(AppError):
    status_code = 403
    code = "cross_org_access"
    message = "Cross-organization access is not permitted"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
    message = "Rate limit exceeded"

    def __init__(self, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retry_after = retry_after


class InferenceUnavailableError(AppError):
    status_code = 503
    code = "inference_unavailable"
    message = "Inference engine is unavailable"


class InferenceTimeoutError(AppError):
    status_code = 504
    code = "inference_timeout"
    message = "Inference request timed out"


class ModelNotLoadedError(AppError):
    status_code = 422
    code = "model_not_loaded"
    message = "Model is registered but not currently loaded"
