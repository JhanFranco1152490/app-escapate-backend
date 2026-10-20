import pytest

from app.accounts.models import LoginMethod
from app.accounts.services.sessions import open_session
from app.core.security.csrf import CSRF_HEADER
from tests.accounts.helpers import MANAGE_USERS, VIEW_USERS
from tests.factories import UserAccountFactory

READ_ENDPOINTS = [
    ("get", "/api/users"),
    ("get", "/api/users/1"),
    ("get", "/api/users/1/logins"),
    ("get", "/api/roles"),
]
WRITE_ENDPOINTS = [
    ("post", "/api/users"),
    ("put", "/api/users/1"),
    ("post", "/api/users/1/deactivate"),
    ("post", "/api/users/1/activate"),
    ("post", "/api/users/1/invitation"),
    ("delete", "/api/users/1/google"),
]


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_every_endpoint_requires_a_session(csrf_client, method, path):
    response = csrf_client.request(method, path)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_every_endpoint_requires_its_permission(auth_client, method, path):
    client = auth_client(permissions=[])

    response = client.request(method, path)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_users_is_not_enough_to_change_them(auth_client, method, path):
    client = auth_client(permissions=VIEW_USERS)

    assert client.request(method, path).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(auth_client, method, path):
    client = auth_client(permissions=MANAGE_USERS)
    del client.headers[CSRF_HEADER]

    response = client.request(method, path)

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.parametrize(
    "path", ["/api/users/0", "/api/users/abc", "/api/users/99999999999999999999"]
)
def test_an_id_that_cannot_exist_is_a_validation_error(auth_client, path):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get(path)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_the_list_returns_the_summary_of_each_user_in_the_common_page_shape(auth_client):
    client = auth_client(permissions=VIEW_USERS)
    UserAccountFactory(first_name="Zoe", last_name="Zapata", password_hash=None)

    body = client.get("/api/users").json()

    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    zoe = body["results"][-1]
    assert set(zoe) == {
        "id",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "role",
        "is_active",
        "invitation_pending",
        "last_activity_at",
    }
    assert zoe["full_name"] == "Zoe Zapata" and zoe["invitation_pending"] is True
    assert set(zoe["role"]) == {"id", "name"}


def test_the_list_hides_the_document_the_phone_and_the_secrets(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    text = client.get("/api/users").text

    for hidden in ("document_number", "phone", "password_hash", "google_sub"):
        assert hidden not in text


def test_the_list_takes_search_filters_and_paging_from_the_query(auth_client, advisor_role):
    client = auth_client(permissions=VIEW_USERS)
    for index in range(3):
        UserAccountFactory(first_name="Ana", last_name=f"Gómez{index}", role=advisor_role)
    UserAccountFactory(first_name="Ana", last_name="Inactiva", role=advisor_role, is_active=False)

    page = client.get(
        "/api/users",
        params={"q": "ana", "status": "active", "role_id": advisor_role.id, "page_size": 2},
    ).json()

    assert page["count"] == 3 and len(page["results"]) == 2
    assert "page=2" in page["next"] and "q=ana" in page["next"]


@pytest.mark.parametrize(
    "params, field",
    [
        ({"status": "deleted"}, "status"),
        ({"role_id": 0}, "role_id"),
        ({"q": "x" * 101}, "q"),
    ],
)
def test_invalid_filters_are_validation_errors(auth_client, params, field):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get("/api/users", params=params)

    assert response.status_code == 422
    assert field in response.json()["fields"]


def test_a_page_beyond_the_end_is_not_found(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get("/api/users", params={"page": 5})

    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_the_detail_shows_the_registered_data(auth_client):
    client = auth_client(permissions=VIEW_USERS)
    user = UserAccountFactory(google_sub="google-sub-7")

    body = client.get(f"/api/users/{user.id}").json()

    assert body["document_type"] == "CC" and body["document_number"] == user.document_number
    assert body["phone"] == user.phone and body["email"] == user.email
    assert (body["has_password"], body["google_linked"]) == (True, True)
    assert body["role"]["id"] == user.role_id
    assert not {"password_hash", "google_sub"} & set(body)


def test_the_detail_of_an_unknown_user_is_not_found(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get("/api/users/999999999")

    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_the_login_history_lists_the_sessions_without_the_ip(auth_client, session):
    client = auth_client(permissions=VIEW_USERS)
    user = UserAccountFactory()
    open_session(session, user, LoginMethod.GOOGLE, "10.1.1.1")

    body = client.get(f"/api/users/{user.id}/logins").json()

    assert body["count"] == 1
    assert set(body["results"][0]) == {"created_at", "method"}
    assert body["results"][0]["method"] == "google"
    assert "10.1.1.1" not in str(body)


def test_the_login_history_of_an_unknown_user_is_not_found(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    assert client.get("/api/users/999999999/logins").status_code == 404


def test_roles_are_listed_for_the_selector(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get("/api/roles")

    assert response.status_code == 200
    names = {role["name"] for role in response.json()}
    assert {"Administrador", "Asesor comercial", "Encargado de proveedores", "Operativo"} <= names
    assert all(set(role) == {"id", "name"} for role in response.json())


def test_the_openapi_describes_the_user_endpoints(app):
    schema = app.openapi()

    assert {"/api/users", "/api/users/{user_id}", "/api/roles"} <= set(schema["paths"])
    listing = schema["paths"]["/api/users"]["get"]["responses"]["200"]
    assert "Page_UserListItem_" in str(listing)
    history = schema["paths"]["/api/users/{user_id}/logins"]["get"]["responses"]["200"]
    assert "Page_LoginEventItem_" in str(history)


def test_a_nul_character_in_the_search_is_a_validation_error_not_a_server_error(auth_client):
    client = auth_client(permissions=VIEW_USERS)

    response = client.get("/api/users", params={"q": "ana\x00"})

    assert response.status_code == 422
    assert "q" in response.json()["fields"]
