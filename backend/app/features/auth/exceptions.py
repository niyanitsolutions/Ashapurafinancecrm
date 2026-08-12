from fastapi import status

from app.core.exceptions import AppError


class InvalidCredentialsError(AppError):
    code = "invalid_credentials"
    http_status = status.HTTP_401_UNAUTHORIZED


class AccountLockedError(AppError):
    code = "account_locked"
    http_status = status.HTTP_423_LOCKED


class AlreadyRegisteredError(AppError):
    code = "already_registered"
    http_status = status.HTTP_409_CONFLICT


class InvalidTicketError(AppError):
    code = "invalid_or_expired_ticket"
    http_status = status.HTTP_401_UNAUTHORIZED


class InvalidRoleForSignupError(AppError):
    code = "invalid_role_for_signup"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class InvalidRefreshTokenError(AppError):
    code = "invalid_refresh_token"
    http_status = status.HTTP_401_UNAUTHORIZED
