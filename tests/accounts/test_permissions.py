import pytest

from app.accounts.permissions import PERMISSIONS, PermissionInfo, check_requires


def test_the_registry_lists_the_permissions_in_matrix_order():
    assert list(PERMISSIONS) == [
        "users.view",
        "users.manage",
        "roles.view",
        "roles.manage",
        "clients.view",
        "clients.manage",
        "travelers.view",
        "travelers.manage",
        "suppliers.view",
        "suppliers.manage",
    ]


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


ADMIN_LEVEL_WARNING = "Dalo solo a quien le confiarías el rol Administrador."


def test_every_permission_explains_what_it_allows():
    # La matriz solo dice "Ver" o "Gestionar": sin la explicación no se sabe qué incluye.
    without_help = [code for code, info in PERMISSIONS.items() if not info.help]

    assert without_help == []


def test_only_the_administrator_level_permissions_carry_the_warning_after_the_explanation():
    warned = [code for code, info in PERMISSIONS.items() if ADMIN_LEVEL_WARNING in info.help]

    assert warned == ["users.manage", "roles.manage"]
    for code in warned:
        explanation, _, _ = PERMISSIONS[code].help.partition("Permite ")
        assert explanation.strip() and PERMISSIONS[code].help.endswith(ADMIN_LEVEL_WARNING)


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
