from typing import Any


class AppError(Exception):
    """Business error translated into a JSON HTTP response by the API layer."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"


class AuthenticationFailed(AppError):
    status_code = 401
    code = "unauthenticated"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
