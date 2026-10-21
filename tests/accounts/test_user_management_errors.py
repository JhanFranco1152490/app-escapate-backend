import pytest

from app.accounts.dependencies import require_permission
from app.accounts.errors import (
    AccountInactive,
    CannotDeactivateSelf,
    DuplicateUser,
    EmailDeliveryFailed,
    InvalidFields,
    InvalidPassword,
    InvitationNotPending,
    LastUserManager,
    UserInactive,
)
from app.accounts.permissions import PERMISSIONS


@pytest.mark.parametrize(
    "error, status_code, code",
    [
        (CannotDeactivateSelf, 409, "cannot_deactivate_self"),
        (LastUserManager, 409, "last_user_manager"),
        (InvitationNotPending, 409, "invitation_not_pending"),
        (UserInactive, 409, "user_inactive"),
        (EmailDeliveryFailed, 502, "email_delivery_failed"),
    ],
)
def test_each_error_has_its_status_and_code(error, status_code, code):
    raised = error()

    assert (raised.status_code, raised.code) == (status_code, code)
    assert raised.detail and raised.fields == {}


def test_user_inactive_does_not_reuse_the_login_error_code():
    assert UserInactive.code != AccountInactive.code


def test_duplicates_name_each_taken_field():
    error = DuplicateUser(["email", "phone"])

    assert (error.status_code, error.code) == (422, "validation_error")
    assert error.fields == {
        "email": ["Ya existe un usuario con ese correo."],
        "phone": ["Ya existe un usuario con ese teléfono."],
    }


def test_the_document_duplicate_has_its_own_message():
    assert DuplicateUser(["document_number"]).fields == {
        "document_number": ["Ya existe un usuario con ese documento."]
    }


def test_field_errors_share_one_shape_with_the_password_error():
    assert issubclass(InvalidPassword, InvalidFields)
    error = InvalidFields(fields={"role_id": ["El rol no existe."]})

    assert (error.status_code, error.code) == (422, "validation_error")
    assert error.fields == {"role_id": ["El rol no existe."]}


def test_user_permissions_are_registered():
    assert {"users.view", "users.manage"} <= set(PERMISSIONS)
    require_permission("users.view")
    require_permission("users.manage")


def test_an_unregistered_permission_fails_when_the_route_is_declared():
    with pytest.raises(ValueError):
        require_permission("users.fly")
