from collections.abc import Iterable

from app.common.errors import ApiError, InvalidFields


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


class InvalidResetToken(ApiError):
    status_code, code = 400, "invalid_reset_token"
    detail = "El enlace no es válido o ya venció."


class InvalidPassword(InvalidFields):
    """La contraseña nueva no cumple la política o no coincide con su confirmación."""


class DuplicateUser(InvalidFields):
    """Otro usuario ya tiene el mismo correo, documento o teléfono."""

    _LABELS = {"email": "correo", "document_number": "documento", "phone": "teléfono"}

    def __init__(self, taken: Iterable[str]):
        super().__init__(
            fields={
                field: [f"Ya existe un usuario con ese {self._LABELS[field]}."] for field in taken
            }
        )


class CannotDeactivateSelf(ApiError):
    status_code, code = 409, "cannot_deactivate_self"
    detail = "No puedes desactivar tu propia cuenta."


class LastUserManager(ApiError):
    status_code, code = 409, "last_user_manager"
    detail = "Debe quedar al menos una persona activa que pueda gestionar usuarios."


class InvitationNotPending(ApiError):
    status_code, code = 409, "invitation_not_pending"
    detail = "Esta persona ya creó su contraseña."


class UserInactive(ApiError):
    """Distinto de `AccountInactive` (403 del ingreso): aquí es el administrador quien actúa."""

    status_code, code = 409, "user_inactive"
    detail = "La cuenta está inactiva. Actívala para enviarle la invitación."


class EmailDeliveryFailed(ApiError):
    status_code, code = 502, "email_delivery_failed"
    detail = "No pudimos enviar el correo. Inténtalo de nuevo."


class RoleProtected(ApiError):
    status_code, code = 409, "role_protected"
    detail = "El rol Administrador no se puede renombrar, borrar ni cambiar sus permisos."


class CannotEditOwnRole(ApiError):
    status_code, code = 409, "cannot_edit_own_role"
    detail = "No puedes cambiar los permisos del rol que tienes asignado."


class RoleInUse(ApiError):
    status_code, code = 409, "role_in_use"
    detail = "Este rol tiene usuarios asignados. Cámbiales el rol antes de borrarlo."


class CannotChangeOwnRole(ApiError):
    status_code, code = 409, "cannot_change_own_role"
    detail = "No puedes cambiar tu propio rol."
