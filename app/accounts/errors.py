from app.common.errors import ApiError


class InvalidCredentials(ApiError):
    status_code, code = 401, "invalid_credentials"
    detail = "El documento o la contraseña no son válidos."


class AccountInactive(ApiError):
    status_code, code = 403, "account_inactive"
    detail = (
        "Tu cuenta está inactiva. Si crees que es un error, escribe a un administrador de la "
        "agencia."
    )


class AccountLocked(ApiError):
    status_code, code = 429, "account_locked"
    detail = "Demasiados intentos fallidos. Inténtalo de nuevo en 15 minutos."
