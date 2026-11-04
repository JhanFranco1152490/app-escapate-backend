import pytest

from app.clients.schemas import ClientFilters
from app.clients.services import client_queries
from app.common.errors import NotFound
from app.common.pagination import PageParams
from tests.factories import ClientFactory, UserAccountFactory
from tests.http import fake_request
from tests.statements import recorded_statements


def search(session, **filters):
    params = PageParams(page=1, page_size=50)
    return client_queries.list_clients(session, ClientFilters(**filters), params, fake_request())


def names(page) -> list[str]:
    return [client.display_name for client in page.results]


@pytest.fixture
def clients(session):
    """Tres personas (una con tilde y sin documento) y una empresa."""
    return {
        "marcela": ClientFactory(
            first_name="Marcela",
            last_name="Gómez Ortiz",
            document_type="CC",
            document_number="1020304050",
            phone="+573001112233",
            email="marcela.gomez@example.com",
        ),
        "julian": ClientFactory(
            first_name="Julián",
            last_name="Gómez Prieto",
            document_type="CC",
            document_number="80112233",
            phone="+573102223344",
            email="julian@example.com",
        ),
        "empresa": ClientFactory(
            company=True,
            business_name="Viajes del Norte SAS",
            document_type="NIT",
            document_number="8001972684",
            phone="+576012345678",
            email="reservas@viajesnorte.example.com",
        ),
        "alvaro": ClientFactory(
            first_name="Álvaro",
            last_name="Pérez",
            document_type=None,
            document_number=None,
            phone="+584125550101",
            email=None,
        ),
    }


def test_the_list_is_ordered_by_display_name_without_accents(session, clients):
    assert names(search(session)) == [
        "Álvaro Pérez",
        "Julián Gómez Prieto",
        "Marcela Gómez Ortiz",
        "Viajes del Norte SAS",
    ]


def test_clients_with_the_same_name_keep_a_stable_order(session):
    first = ClientFactory(first_name="Ana", last_name="Gómez")
    second = ClientFactory(first_name="Ana", last_name="Gómez")

    assert [client.id for client in search(session).results] == [first.id, second.id]


def test_the_list_is_paginated(session):
    for _ in range(5):
        ClientFactory()

    page = client_queries.list_clients(
        session, ClientFilters(), PageParams(page=2, page_size=2), fake_request(query="page=2")
    )

    assert (page.count, len(page.results)) == (5, 2)
    assert "page=1" in page.previous and "page=3" in page.next


def test_filtering_by_client_type(session, clients):
    assert names(search(session, client_type="company")) == ["Viajes del Norte SAS"]
    assert search(session, client_type="person").count == 3


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("gomez marcela", ["Marcela Gómez Ortiz"], id="words-in-any-order"),
        pytest.param("góm", ["Julián Gómez Prieto", "Marcela Gómez Ortiz"], id="part-of-a-word"),
        pytest.param("GOMEZ", ["Julián Gómez Prieto", "Marcela Gómez Ortiz"], id="uppercase"),
        pytest.param("julian", ["Julián Gómez Prieto"], id="without-the-accent"),
        pytest.param("alvaro", ["Álvaro Pérez"], id="accent-on-the-first-letter"),
        pytest.param("norte viajes", ["Viajes del Norte SAS"], id="business-name"),
    ],
)
def test_searching_by_name(session, clients, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("1.020.30", ["Marcela Gómez Ortiz"], id="start-with-dots"),
        pytest.param("1020304050", ["Marcela Gómez Ortiz"], id="whole-number"),
        pytest.param("800.197", ["Viajes del Norte SAS"], id="start-of-a-nit"),
        pytest.param("0304", [], id="middle-of-a-number"),
    ],
)
def test_searching_by_the_start_of_the_document(session, clients, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("viajesnorte", ["Viajes del Norte SAS"], id="part-of-the-domain"),
        pytest.param("MARCELA.GOMEZ@", ["Marcela Gómez Ortiz"], id="uppercase"),
    ],
)
def test_searching_by_part_of_the_email(session, clients, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("300 111", ["Marcela Gómez Ortiz"], id="with-spaces"),
        pytest.param("+57 300 111", ["Marcela Gómez Ortiz"], id="with-the-country-code"),
        pytest.param("(310) 222-33", ["Julián Gómez Prieto"], id="with-separators"),
        pytest.param("412 555", ["Álvaro Pérez"], id="foreign-number"),
        pytest.param("300", ["Marcela Gómez Ortiz"], id="three-digits"),
        pytest.param("30", [], id="two-digits-are-too-few"),
        pytest.param("300abc", [], id="not-only-digits"),
    ],
)
def test_searching_by_part_of_the_phone(session, clients, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize("q", ["%", "_", "\\", "G_mez", "G%z"])
def test_like_wildcards_are_searched_literally(session, clients, q):
    assert names(search(session, q=q)) == []


def test_words_after_the_fifth_are_ignored(session, clients):
    # Las cinco primeras coinciden; si "sobra" contara, no encontraría a nadie.
    assert names(search(session, q="marcela gómez ortiz marcela gómez sobra")) == [
        "Marcela Gómez Ortiz"
    ]


def test_the_list_needs_only_the_count_and_the_page(session, clients):
    session.expire_all()
    with recorded_statements(session) as statements:
        page = search(session)

    assert page.count == 4
    assert len(statements) == 2


def test_get_client_loads_who_registered_it_in_the_same_query(session):
    advisor = UserAccountFactory(first_name="Laura", last_name="Rojas")
    client = ClientFactory(created_by=advisor)
    # Una petición nueva empieza con la sesión vacía.
    session.expunge_all()
    with recorded_statements(session) as statements:
        found = client_queries.get_client(session, client.id)
        who = (found.created_by.full_name, found.data_consent_by.full_name)

    assert who == ("Laura Rojas", "Laura Rojas")
    assert len(statements) == 1


def test_get_client_of_an_unknown_id_is_not_found(session):
    with pytest.raises(NotFound):
        client_queries.get_client(session, 999_999_999)
