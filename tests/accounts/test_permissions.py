import pytest

from app.accounts.permissions import PERMISSIONS, PermissionInfo, check_requires


def test_the_registry_lists_the_permissions_in_matrix_order():
    assert list(PERMISSIONS) == ["users.view", "users.manage", "roles.view", "roles.manage"]


def test_each_permission_has_its_place_in_the_matrix():
    manage_users = PERMISSIONS["users.manage"]

    assert manage_users.section == "Administración"
    assert manage_users.group == "Usuarios"
    assert manage_users.label == "Gestionar"
    assert manage_users.description == "Gestionar usuarios"
    assert manage_users.requires == ("users.view",)


def test_managing_requires_viewing():
    assert PERMISSIONS["users.manage"].requires == ("users.view",)
    assert PERMISSIONS["roles.manage"].requires == ("roles.view",)
    assert PERMISSIONS["users.view"].requires == ()
    assert PERMISSIONS["roles.view"].requires == ()


def test_only_the_administrator_level_permissions_carry_a_warning():
    with_help = [code for code, info in PERMISSIONS.items() if info.help]

    assert with_help == ["users.manage", "roles.manage"]


def test_every_required_code_is_registered():
    for info in PERMISSIONS.values():
        assert set(info.requires) <= set(PERMISSIONS)


def test_a_required_code_outside_the_registry_fails():
    registry = {
        "things.manage": PermissionInfo(
            section="Pruebas",
            group="Cosas",
            label="Gestionar",
            description="Gestionar cosas",
            requires=("things.veiw",),
        )
    }

    with pytest.raises(ValueError, match="things.veiw"):
        check_requires(registry)
