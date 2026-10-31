import pytest
from sqlmodel import select

from app.accounts.models import RefreshToken, RolePermission
from app.accounts.permissions import PERMISSIONS
from app.core.security.csrf import CSRF_HEADER
from tests.accounts.helpers import signed_in
from tests.factories import RoleFactory, UserAccountFactory

VIEW_ROLES = ["roles.view"]
MANAGE_ROLES = ["roles.view", "roles.manage"]

READ_ENDPOINTS = [
    ("get", "/api/permissions"),
    ("get", "/api/roles"),
    ("get", "/api/roles/1"),
]
WRITE_ENDPOINTS = [
    ("post", "/api/roles"),
    ("put", "/api/roles/1"),
    ("delete", "/api/roles/1"),
    ("put", "/api/users/1/role"),
]


def grant(session, role, *codes):
    session.add_all(RolePermission(role_id=role.id, permission=code) for code in codes)
    session.flush()


def body(name="Ventas", description=None, permissions=()):
    return {"name": name, "description": description, "permissions": list(permissions)}


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_every_endpoint_requires_a_session(csrf_client, method, path):
    response = csrf_client.request(method, path)

    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_every_endpoint_requires_a_permission(auth_client, method, path):
    response = auth_client().request(method, path)

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS[:3])
def test_viewing_roles_is_not_enough_to_change_them(auth_client, method, path):
    assert auth_client(permissions=VIEW_ROLES).request(method, path).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_mutations_require_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE_ROLES + ["users.view", "users.manage"])
    del client.headers[CSRF_HEADER]

    assert client.request(method, path).status_code == 403


@pytest.mark.parametrize("permissions", [["users.view"], ["roles.view"]])
def test_the_role_list_accepts_viewing_users_or_roles(auth_client, permissions):
    assert auth_client(permissions=permissions).get("/api/roles").status_code == 200


@pytest.mark.parametrize("path", ["/api/permissions", "/api/roles/{id}"])
@pytest.mark.parametrize(
    "permissions, status_code",
    [(["roles.view"], 200), (["users.view", "users.manage"], 200), (["users.view"], 403)],
)
def test_the_role_detail_and_catalog_accept_viewing_roles_or_managing_users(
    auth_client, advisor_role, path, permissions, status_code
):
    response = auth_client(permissions=permissions).get(path.format(id=advisor_role.id))

    assert response.status_code == status_code


# --- Forma de las respuestas ---------------------------------------------------------------


def test_the_catalog_lists_every_permission_in_order(auth_client):
    response = auth_client(permissions=VIEW_ROLES).get("/api/permissions")

    assert [item["code"] for item in response.json()] == list(PERMISSIONS)
    assert set(response.json()[0]) == {
        "code",
        "section",
        "group",
        "label",
        "description",
        "requires",
        "help",
    }


def test_the_list_shows_each_role_with_its_counts(auth_client):
    role = RoleFactory(name="Bodega")
    UserAccountFactory(role=role, is_active=False)

    roles = auth_client(permissions=VIEW_ROLES).get("/api/roles").json()

    bodega = next(item for item in roles if item["name"] == "Bodega")
    assert bodega == {
        "id": role.id,
        "name": "Bodega",
        "description": None,
        "is_protected": False,
        "user_count": 1,
        "inactive_user_count": 1,
    }


def test_a_role_detail_has_its_permissions(auth_client, administrator_role):
    response = auth_client(permissions=VIEW_ROLES).get(f"/api/roles/{administrator_role.id}")

    detail = response.json()
    assert detail["is_protected"] is True
    assert detail["permissions"] == sorted(PERMISSIONS)
    assert {"created_at", "updated_at"} <= set(detail)


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_an_unknown_role_is_not_found(auth_client, method):
    client = auth_client(permissions=MANAGE_ROLES)

    response = client.request(method, "/api/roles/999999999", json=body())

    assert response.status_code == 404


@pytest.mark.parametrize("role_id", ["0", "abc", str(2**63)])
def test_an_impossible_id_is_a_validation_error(auth_client, role_id):
    response = auth_client(permissions=VIEW_ROLES).get(f"/api/roles/{role_id}")

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")


# --- Crear, editar, borrar -----------------------------------------------------------------


def test_creating_a_role_answers_201_with_its_detail(auth_client):
    response = auth_client(permissions=MANAGE_ROLES).post(
        "/api/roles", json=body(permissions=["users.view"])
    )

    assert response.status_code == 201
    assert (response.json()["name"], response.json()["permissions"]) == ("Ventas", ["users.view"])


def test_field_errors_come_back_in_their_field(auth_client):
    RoleFactory(name="Ventas")
    client = auth_client(permissions=MANAGE_ROLES)

    taken = client.post("/api/roles", json=body(name="ventas"))
    missing = client.post("/api/roles", json=body(name="Otro", permissions=["users.manage"]))

    assert taken.status_code == 422 and set(taken.json()["fields"]) == {"name"}
    assert missing.json()["fields"] == {
        "permissions": ["Gestionar usuarios necesita Ver usuarios."]
    }


def test_sending_is_protected_is_rejected(auth_client):
    response = auth_client(permissions=MANAGE_ROLES).post(
        "/api/roles", json=body() | {"is_protected": True}
    )

    assert response.status_code == 422
    assert "is_protected" in response.json()["fields"]


def test_the_protected_role_answers_409(auth_client, administrator_role):
    client = auth_client(permissions=MANAGE_ROLES)
    renamed = body(name="Dirección", permissions=list(PERMISSIONS))

    for response in [
        client.put(f"/api/roles/{administrator_role.id}", json=renamed),
        client.delete(f"/api/roles/{administrator_role.id}"),
    ]:
        assert (response.status_code, response.json()["code"]) == (409, "role_protected")


def test_editing_and_deleting_a_role(auth_client):
    role = RoleFactory(name="Ventas")
    client = auth_client(permissions=MANAGE_ROLES)

    edited = client.put(
        f"/api/roles/{role.id}", json=body(description="Nueva.", permissions=["roles.view"])
    )
    deleted = client.delete(f"/api/roles/{role.id}")

    assert edited.status_code == 200 and edited.json()["description"] == "Nueva."
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"/api/roles/{role.id}").status_code == 404


def test_a_role_in_use_cannot_be_deleted(auth_client):
    role = RoleFactory()
    UserAccountFactory(role=role)

    response = auth_client(permissions=MANAGE_ROLES).delete(f"/api/roles/{role.id}")

    assert (response.status_code, response.json()["code"]) == (409, "role_in_use")


def test_nobody_changes_the_permissions_of_their_own_role(app, session):
    role = RoleFactory(name="Gerencia")
    grant(session, role, *MANAGE_ROLES)
    client = signed_in(app, session, UserAccountFactory(role=role))

    response = client.put(f"/api/roles/{role.id}", json=body(name="Gerencia"))

    assert (response.status_code, response.json()["code"]) == (409, "cannot_edit_own_role")


# --- HU-04 de punta a punta ----------------------------------------------------------------


def test_removing_and_giving_back_a_permission_applies_on_the_next_request(app, session):
    """CA-04 y CA-06: la misma sesión de la persona pierde el acceso en su siguiente petición
    y lo recupera, sin volver a entrar."""
    role = RoleFactory(name="Consulta")
    grant(session, role, "users.view")
    person = signed_in(app, session, UserAccountFactory(role=role))
    admin_role = RoleFactory(name="Gerencia")
    grant(session, admin_role, *MANAGE_ROLES)
    admin = signed_in(app, session, UserAccountFactory(role=admin_role))

    assert person.get("/api/users").status_code == 200

    removed = admin.put(f"/api/roles/{role.id}", json=body(name="Consulta"))
    assert removed.status_code == 200
    denied = person.get("/api/users")
    assert (denied.status_code, denied.json()["code"]) == (403, "permission_denied")

    given = admin.put(
        f"/api/roles/{role.id}", json=body(name="Consulta", permissions=["users.view"])
    )
    assert given.status_code == 200
    assert person.get("/api/users").status_code == 200


# --- HU-05 ---------------------------------------------------------------------------------


def test_changing_a_role_from_the_api_applies_to_the_open_session(
    app, session, auth_client, advisor_role, sent
):
    """CA-01 a CA-04: la persona cambia de rol con la sesión abierta y en su siguiente
    petición tiene los permisos del rol nuevo y pierde los del anterior."""
    viewers = RoleFactory(name="Consulta")
    grant(session, viewers, "users.view")
    user = UserAccountFactory(role=viewers)
    person = signed_in(app, session, user)
    admin = auth_client(permissions=["users.view", "users.manage"])

    assert person.get("/api/users").status_code == 200
    response = admin.put(f"/api/users/{user.id}/role", json={"role_id": advisor_role.id})

    assert response.status_code == 200
    assert response.json()["role"] == {"id": advisor_role.id, "name": "Asesor comercial"}
    me = person.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["permissions"] == [
        "clients.manage",
        "clients.view",
        "suppliers.view",
        "travelers.manage",
        "travelers.view",
    ]
    assert person.get("/api/users").status_code == 403
    tokens = session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).all()
    assert all(token.revoked_at is None for token in tokens)


def test_changing_a_role_answers_its_errors(auth_client, advisor_role):
    admin = auth_client(permissions=["users.view", "users.manage"])
    user = UserAccountFactory(role=advisor_role)

    unknown_role = admin.put(f"/api/users/{user.id}/role", json={"role_id": 999_999_999})
    unknown_user = admin.put("/api/users/999999999/role", json={"role_id": advisor_role.id})

    assert unknown_role.status_code == 422
    assert unknown_role.json()["fields"] == {"role_id": ["El rol no existe."]}
    assert unknown_user.status_code == 404


def test_nobody_changes_their_own_role_from_the_api(app, session, advisor_role):
    managers = RoleFactory(name="Gerencia")
    grant(session, managers, "users.view", "users.manage")
    user = UserAccountFactory(role=managers)

    response = signed_in(app, session, user).put(
        f"/api/users/{user.id}/role", json={"role_id": advisor_role.id}
    )

    assert (response.status_code, response.json()["code"]) == (409, "cannot_change_own_role")


def test_the_openapi_describes_the_role_endpoints(app):
    paths = set(app.openapi()["paths"])

    assert {
        "/api/permissions",
        "/api/roles",
        "/api/roles/{role_id}",
        "/api/users/{user_id}/role",
    } <= paths
