import logging

from app.accounts.models import UserAccount
from tests.accounts.conftest import LEAKY_PROVIDER_MESSAGE
from tests.accounts.helpers import MANAGE_USERS, NEW_USER, login, second_client
from tests.factories import UserAccountFactory


def create(client, role_id, **overrides):
    return client.post("/api/users", json=NEW_USER | overrides | {"role_id": role_id})


def test_creating_a_user_answers_201_with_the_account_and_the_invitation(
    auth_client, advisor_role, sent
):
    client = auth_client(permissions=MANAGE_USERS)

    response = create(client, advisor_role.id)

    assert response.status_code == 201
    body = response.json()
    assert body["invitation_sent"] is True
    user = body["user"]
    assert (user["full_name"], user["email"], user["phone"]) == (
        "Laura Rojas",
        NEW_USER["email"],
        NEW_USER["phone"],
    )
    assert (user["is_active"], user["has_password"], user["invitation_pending"]) == (
        True,
        False,
        True,
    )
    assert user["role"]["id"] == advisor_role.id
    assert [email["to"] for email in sent] == [NEW_USER["email"]]


def test_missing_required_data_lists_every_pending_field(auth_client, advisor_role, sent):
    client = auth_client(permissions=MANAGE_USERS)

    response = client.post("/api/users", json={"role_id": advisor_role.id})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert set(response.json()["fields"]) == set(NEW_USER)
    assert sent == []


def test_invalid_values_are_reported_in_spanish_on_their_field(auth_client, advisor_role):
    client = auth_client(permissions=MANAGE_USERS)

    response = create(client, advisor_role.id, phone="123", email="x", first_name=" ")

    fields = response.json()["fields"]
    assert fields["phone"] == ["Debe ser un celular colombiano de 10 dígitos."]
    assert fields["email"] == ["No es un correo válido."]
    assert fields["first_name"] == ["Este campo es obligatorio."]


def test_creating_with_an_unknown_role_or_a_repeated_value_is_a_validation_error(
    auth_client, advisor_role
):
    client = auth_client(permissions=MANAGE_USERS)
    UserAccountFactory(email=NEW_USER["email"], phone=NEW_USER["phone"])

    unknown_role = create(client, 999_999_999)
    repeated = create(client, advisor_role.id)

    assert unknown_role.status_code == 422
    assert unknown_role.json()["fields"] == {"role_id": ["El rol no existe."]}
    assert repeated.status_code == 422
    assert set(repeated.json()["fields"]) == {"email", "phone"}


def test_creating_with_a_mail_failure_answers_201_and_says_the_invitation_failed(
    auth_client, advisor_role, email_down, caplog
):
    client = auth_client(permissions=MANAGE_USERS)

    with caplog.at_level(logging.DEBUG):
        response = create(client, advisor_role.id)

    assert response.status_code == 201 and response.json()["invitation_sent"] is False
    assert LEAKY_PROVIDER_MESSAGE not in caplog.text and NEW_USER["email"] not in caplog.text


def test_editing_answers_with_the_saved_account_and_rejects_what_is_not_editable(auth_client):
    client = auth_client(permissions=MANAGE_USERS)
    user = UserAccountFactory()

    response = client.put(f"/api/users/{user.id}", json=NEW_USER)

    assert response.status_code == 200
    assert response.json()["invitation_sent"] is None
    assert response.json()["user"]["full_name"] == "Laura Rojas"
    for extra in ({"role_id": 1}, {"is_active": False}, {"password": "x" * 12}):
        rejected = client.put(f"/api/users/{user.id}", json=NEW_USER | extra)
        assert rejected.status_code == 422


def test_editing_an_unknown_user_is_not_found_and_a_repeat_is_a_validation_error(auth_client):
    client = auth_client(permissions=MANAGE_USERS)
    UserAccountFactory(phone=NEW_USER["phone"])
    user = UserAccountFactory()

    assert client.put("/api/users/999999999", json=NEW_USER).status_code == 404
    repeated = client.put(f"/api/users/{user.id}", json=NEW_USER)
    assert repeated.status_code == 422 and list(repeated.json()["fields"]) == ["phone"]


def test_deactivating_returns_the_inactive_account(auth_client):
    client = auth_client(permissions=MANAGE_USERS)
    user = UserAccountFactory()

    response = client.post(f"/api/users/{user.id}/deactivate")

    assert response.status_code == 200 and response.json()["is_active"] is False


def test_nobody_can_deactivate_themselves_through_the_api(auth_client, session):
    client = auth_client(permissions=MANAGE_USERS)
    me = client.get("/api/auth/me").json()["id"]

    response = client.post(f"/api/users/{me}/deactivate")

    assert response.status_code == 409
    assert response.json()["code"] == "cannot_deactivate_self"
    assert session.get(UserAccount, me).is_active


def test_deactivating_and_activating_an_unknown_user_is_not_found(auth_client):
    client = auth_client(permissions=MANAGE_USERS)

    assert client.post("/api/users/999999999/deactivate").status_code == 404
    assert client.post("/api/users/999999999/activate").status_code == 404


def test_activating_returns_the_active_account(auth_client):
    client = auth_client(permissions=MANAGE_USERS)
    user = UserAccountFactory(is_active=False)

    response = client.post(f"/api/users/{user.id}/activate")

    assert response.status_code == 200 and response.json()["is_active"] is True


def test_the_invitation_can_be_resent_until_the_password_exists(auth_client, sent):
    client = auth_client(permissions=MANAGE_USERS)
    pending = UserAccountFactory(password_hash=None)
    done = UserAccountFactory()
    inactive = UserAccountFactory(password_hash=None, is_active=False)

    assert client.post(f"/api/users/{pending.id}/invitation").status_code == 204
    assert [email["to"] for email in sent] == [pending.email]
    refused = client.post(f"/api/users/{done.id}/invitation")
    assert (refused.status_code, refused.json()["code"]) == (409, "invitation_not_pending")
    refused = client.post(f"/api/users/{inactive.id}/invitation")
    assert (refused.status_code, refused.json()["code"]) == (409, "user_inactive")
    assert client.post("/api/users/999999999/invitation").status_code == 404


def test_a_mail_failure_when_resending_is_a_502(auth_client, email_down):
    client = auth_client(permissions=MANAGE_USERS)
    pending = UserAccountFactory(password_hash=None)

    response = client.post(f"/api/users/{pending.id}/invitation")

    assert (response.status_code, response.json()["code"]) == (502, "email_delivery_failed")


def test_resending_is_limited_per_ip(auth_client, sent):
    client = auth_client(permissions=MANAGE_USERS)
    pending = UserAccountFactory(password_hash=None)

    statuses = [client.post(f"/api/users/{pending.id}/invitation").status_code for _ in range(11)]

    assert statuses == [204] * 10 + [429]
    assert len(sent) == 10


def test_unlinking_google_returns_the_account_without_the_link(auth_client):
    client = auth_client(permissions=MANAGE_USERS)
    user = UserAccountFactory(google_sub="google-sub-8")

    response = client.delete(f"/api/users/{user.id}/google")

    assert response.status_code == 200 and response.json()["google_linked"] is False
    assert client.delete("/api/users/999999999/google").status_code == 404


def test_the_whole_life_of_an_account_from_the_api(auth_client, advisor_role, sent, app):
    """Recorre la vida completa de una cuenta con los endpoints reales."""
    admin = auth_client(permissions=MANAGE_USERS)

    # Se registra y recibe la invitación.
    created = create(admin, advisor_role.id).json()["user"]
    assert created["is_active"] and len(sent) == 1

    # La persona crea su contraseña con el enlace y ya puede entrar con su documento.
    person = second_client(app)
    token = sent[0]["context"]["link"].split("#token=", 1)[1]
    password = "una frase nueva y larga"
    confirmed = person.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": password, "password_confirmation": password},
    )
    assert confirmed.status_code == 200
    assert person.get("/api/auth/me").status_code == 200
    credentials = {"document_number": NEW_USER["document_number"], "password": password}

    # El administrador consulta sus datos registrados.
    detail = admin.get(f"/api/users/{created['id']}").json()
    assert detail["document_number"] == NEW_USER["document_number"]
    assert detail["has_password"] is True

    # Modifica sus datos y se guardan.
    changed = admin.put(
        f"/api/users/{created['id']}", json=NEW_USER | {"last_name": "Rojas Pérez"}
    )
    assert changed.json()["user"]["full_name"] == "Laura Rojas Pérez"
    assert admin.get(f"/api/users/{created['id']}").json()["last_name"] == "Rojas Pérez"

    # Se desactiva; no puede seguir con su sesión ni entrar, y nada se borra.
    assert admin.post(f"/api/users/{created['id']}/deactivate").status_code == 200
    assert person.get("/api/auth/me").status_code == 401
    refused = login(second_client(app), **credentials)
    assert (refused.status_code, refused.json()["code"]) == (403, "account_inactive")
    assert admin.get(f"/api/users/{created['id']}").json()["first_name"] == "Laura"
    assert admin.get(f"/api/users/{created['id']}/logins").json()["count"] >= 1

    # Se activa de nuevo y entra con el rol que tenía.
    assert admin.post(f"/api/users/{created['id']}/activate").status_code == 200
    again = login(second_client(app), **credentials)
    assert again.status_code == 200 and again.json()["role"]["id"] == advisor_role.id


def test_a_nul_character_in_a_name_is_a_validation_error_not_a_server_error(
    auth_client, advisor_role, sent
):
    client = auth_client(permissions=MANAGE_USERS)

    response = create(client, advisor_role.id, first_name="Ana\x00")

    assert response.status_code == 422
    assert response.json()["fields"] == {"first_name": ["Contiene caracteres que no se permiten."]}
    assert sent == []
