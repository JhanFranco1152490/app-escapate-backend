from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlmodel import select

from app.accounts.models import LoginEvent, Role
from app.accounts.schemas import LoginEventItem, UserDetail, UserFilters, UserListItem
from app.accounts.services import user_queries
from app.common.errors import NotFound
from app.common.pagination import PageParams
from tests.factories import RoleFactory, UserAccountFactory
from tests.http import fake_request


def search(session, **filters):
    params = PageParams(page=1, page_size=50)
    return user_queries.list_users(session, UserFilters(**filters), params, fake_request())


def names(page) -> list[str]:
    return [user.full_name for user in page.results]


@pytest.fixture
def team(session):
    """Cuatro personas con nombres con tilde y documentos distintos."""
    return {
        "laura": UserAccountFactory(
            first_name="Laura", last_name="Rojas", document_number="1090123456"
        ),
        "sofia": UserAccountFactory(
            first_name="Sofía", last_name="Barrios", document_number="52111222"
        ),
        "andres": UserAccountFactory(
            first_name="Andrés", last_name="Quintero", document_number="80555666"
        ),
        "mateo": UserAccountFactory(
            first_name="Mateo", last_name="Pardo", document_type="PA", document_number="AB12345"
        ),
    }


def test_the_list_is_ordered_by_name_ignoring_case_and_accents(session):
    for first_name in ["Zoe", "Ana", "álvaro", "alberto"]:
        UserAccountFactory(first_name=first_name, last_name="Pérez")

    page = search(session)

    assert [user.first_name for user in page.results] == ["alberto", "álvaro", "Ana", "Zoe"]


def test_people_with_the_same_name_keep_a_stable_order_by_id(session):
    first = UserAccountFactory(first_name="Ana", last_name="Gómez")
    second = UserAccountFactory(first_name="Ana", last_name="Gómez")

    assert [user.id for user in search(session).results] == [first.id, second.id]


def test_the_list_is_paginated(session):
    for number in range(5):
        UserAccountFactory(first_name=f"Persona{number}", last_name="Prueba")
    params = PageParams(page=2, page_size=2)

    page = user_queries.list_users(session, UserFilters(), params, fake_request(query="page=2"))

    assert page.count == 5
    assert [user.first_name for user in page.results] == ["Persona2", "Persona3"]
    assert "page=1" in page.previous and "page=3" in page.next


def test_the_list_loads_roles_without_a_query_per_user(session):
    for _ in range(6):
        UserAccountFactory()
    session.expire_all()
    statements = []

    def record(connection, cursor, statement, *args):
        statements.append(statement)

    connection = session.get_bind()
    event.listen(connection, "before_cursor_execute", record)
    try:
        page = search(session)
        roles = [user.role.name for user in page.results]
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert len(roles) == 6
    assert len(statements) == 2  # el conteo y la página


def test_filtering_by_status(session):
    active = UserAccountFactory(is_active=True)
    inactive = UserAccountFactory(is_active=False)

    assert [user.id for user in search(session, status="active").results] == [active.id]
    assert [user.id for user in search(session, status="inactive").results] == [inactive.id]
    assert search(session).count == 2


def test_filtering_by_role(session):
    advisor, operator = RoleFactory(), RoleFactory()
    in_advisor = UserAccountFactory(role=advisor)
    UserAccountFactory(role=operator)

    page = search(session, role_id=advisor.id)

    assert [user.id for user in page.results] == [in_advisor.id]


def test_filters_combine(session, team):
    team["laura"].is_active = False
    session.flush()

    assert names(search(session, q="laura", status="active")) == []
    assert names(search(session, q="laura", status="inactive")) == ["Laura Rojas"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("laura", ["Laura Rojas"]),
        ("laura rojas", ["Laura Rojas"]),
        ("rojas laura", ["Laura Rojas"]),
        ("roj", ["Laura Rojas"]),
        ("LAURA", ["Laura Rojas"]),
        ("sofia", ["Sofía Barrios"]),
        ("SOFÍA", ["Sofía Barrios"]),
        ("andres quintero", ["Andrés Quintero"]),
        ("laura barrios", []),
        ("inexistente", []),
        ("   ", ["Andrés Quintero", "Laura Rojas", "Mateo Pardo", "Sofía Barrios"]),
    ],
)
def test_searching_by_name(session, team, text, expected):
    assert names(search(session, q=text)) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1090123456", ["Laura Rojas"]),
        ("1.090.123.456", ["Laura Rojas"]),
        ("1.090.12", ["Laura Rojas"]),
        ("1090 123", ["Laura Rojas"]),
        ("52111222", ["Sofía Barrios"]),
        ("ab12", ["Mateo Pardo"]),
        ("AB-12345", ["Mateo Pardo"]),
        ("090123", []),
        ("99999", []),
    ],
)
def test_searching_by_document_matches_the_beginning(session, team, text, expected):
    assert names(search(session, q=text)) == expected


def test_the_email_and_the_phone_are_not_searched(session):
    UserAccountFactory(email="zzz-unico@example.com", phone="3119998877")

    assert search(session, q="zzz").count == 0
    assert search(session, q="3119998877").count == 0


def test_like_wildcards_are_taken_literally(session):
    UserAccountFactory(first_name="Mario", last_name="Gómez")
    underscore = UserAccountFactory(first_name="Mar_o", last_name="Gómez")
    percent = UserAccountFactory(first_name="Pedro", last_name="100%")

    assert [user.id for user in search(session, q="mar_").results] == [underscore.id]
    assert [user.id for user in search(session, q="100%").results] == [percent.id]
    assert search(session, q="%").count == 1
    assert search(session, q="\\").count == 0


def test_only_the_first_words_are_used(session):
    user = UserAccountFactory(first_name="a b c", last_name="d e")

    page = search(session, q="a b c d e sexta palabra")

    assert [found.id for found in page.results] == [user.id]


def test_a_user_summary_hides_the_secrets_and_flags_the_invitation(session):
    pending = UserAccountFactory(password_hash=None, google_sub=None)
    with_password = UserAccountFactory()
    with_google = UserAccountFactory(password_hash=None, google_sub="google-sub-1")

    assert [pending.invitation_pending, with_password.invitation_pending] == [True, False]
    assert with_google.invitation_pending is False
    item = UserListItem.model_validate(pending).model_dump()
    assert item["invitation_pending"] is True
    assert not {"password_hash", "google_sub", "document_number", "phone"} & set(item)


def test_the_detail_tells_whether_the_password_and_google_are_set(session):
    user = UserAccountFactory(google_sub="google-sub-2")

    detail = UserDetail.model_validate(user).model_dump()

    assert detail["has_password"] is True and detail["google_linked"] is True
    assert "password_hash" not in detail and "google_sub" not in detail
    assert detail["document_number"] == user.document_number and detail["phone"] == user.phone


def test_get_user_returns_the_account_with_its_role(session):
    user = UserAccountFactory()

    found = user_queries.get_user(session, user.id)

    assert found.id == user.id and found.role.id == user.role_id


@pytest.mark.parametrize("user_id", [999_999_999, 2**62])
def test_get_user_raises_not_found_for_an_unknown_id(session, user_id):
    with pytest.raises(NotFound):
        user_queries.get_user(session, user_id)


def add_login(session, user, method, minutes_ago):
    when = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    login = LoginEvent(user_id=user.id, method=method, ip="10.0.0.1", created_at=when)
    session.add(login)
    session.flush()
    return login


def logins(session, user, page=1, page_size=10):
    params = PageParams(page=page, page_size=page_size)
    return user_queries.list_logins(session, user.id, params, fake_request())


def test_logins_are_newest_first_and_cover_the_three_ways(session):
    user = UserAccountFactory()
    add_login(session, user, "document", minutes_ago=30)
    add_login(session, user, "email_link", minutes_ago=20)
    add_login(session, user, "google", minutes_ago=10)

    page = logins(session, user)

    assert [item.method for item in page.results] == ["google", "email_link", "document"]


def test_logins_do_not_mix_users_and_are_paginated(session):
    user, other = UserAccountFactory(), UserAccountFactory()
    for minutes in range(5):
        add_login(session, user, "document", minutes_ago=minutes)
    add_login(session, other, "google", minutes_ago=1)

    first = logins(session, user, page_size=2)
    last = logins(session, user, page=3, page_size=2)

    assert first.count == 5 and len(first.results) == 2 and first.next
    assert len(last.results) == 1 and last.next is None


def test_logins_with_the_same_time_keep_a_stable_order(session):
    user = UserAccountFactory()
    when = datetime.now(UTC)
    ids = []
    for _ in range(3):
        login = LoginEvent(user_id=user.id, method="document", ip="10.0.0.1", created_at=when)
        session.add(login)
        session.flush()
        ids.append(login.id)

    assert [item.id for item in logins(session, user).results] == sorted(ids, reverse=True)


def test_a_user_without_logins_has_an_empty_first_page(session):
    assert logins(session, UserAccountFactory()).results == []


def test_the_login_item_does_not_expose_the_ip(session):
    user = UserAccountFactory()
    add_login(session, user, "document", minutes_ago=1)

    item = LoginEventItem.model_validate(logins(session, user).results[0]).model_dump()

    assert set(item) == {"created_at", "method"}


def test_logins_of_an_unknown_user_raise_not_found(session):
    params = PageParams(page=1, page_size=10)

    with pytest.raises(NotFound):
        user_queries.list_logins(session, 999_999_999, params, fake_request())


def test_roles_are_listed_by_name_with_the_seeded_ones(session):
    roles = user_queries.list_roles(session)

    seeded = ["Administrador", "Asesor comercial", "Encargado de proveedores", "Operativo"]
    assert [role.name for role in roles if role.name in seeded] == seeded
    assert {role.id for role in roles} == set(session.exec(select(Role.id)).all())


@pytest.mark.parametrize("text", [".", "-", " . - . "])
def test_a_search_made_only_of_separators_looks_by_name_and_finds_nothing(session, team, text):
    assert search(session, q=text).count == 0
