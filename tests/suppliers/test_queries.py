import pytest

from app.common.errors import NotFound
from app.common.pagination import PageParams
from app.suppliers.schemas import SupplierFilters
from app.suppliers.services import supplier_queries
from tests.factories import SupplierFactory, UserAccountFactory
from tests.http import fake_request
from tests.statements import recorded_statements


def search(session, **filters):
    params = PageParams(page=1, page_size=50)
    return supplier_queries.list_suppliers(
        session, SupplierFilters(**filters), params, fake_request()
    )


def names(page) -> list[str]:
    return [supplier.trade_name for supplier in page.results]


@pytest.fixture
def suppliers(session):
    """Un hotel con NIT, un operador del exterior, un guía sin documento y una naviera
    inactiva."""
    return {
        "hotel": SupplierFactory(
            trade_name="Hotel Caribe Azul",
            legal_name="Inversiones Costa Brava SAS",
            document_type="NIT",
            document_number="8001972684",
            categories=["lodging", "tours"],
            contact_name="Andrea Pérez Gil",
            contact_email="reservas@caribeazul.example.com",
        ),
        "operador": SupplierFactory(
            trade_name="Andes Tours",
            document_type="FOREIGN",
            document_number="A1234567",
            categories=["tours"],
            contact_name="Mateo Ruiz",
            contact_email="mateo@andestours.example.com",
        ),
        "guia": SupplierFactory(
            trade_name="Árbol de Pan Guías",
            document_type=None,
            document_number=None,
            categories=["tours"],
            contact_name="Lucía Gómez",
        ),
        "naviera": SupplierFactory(
            trade_name="Naviera del Sol",
            document_type="FOREIGN",
            document_number="B7654321",
            categories=["cruise"],
            contact_name="Julián Prieto",
            inactive=True,
        ),
    }


def test_only_active_suppliers_are_listed_by_default_ordered_without_accents(session, suppliers):
    assert names(search(session)) == ["Andes Tours", "Árbol de Pan Guías", "Hotel Caribe Azul"]


def test_filtering_by_status(session, suppliers):
    assert names(search(session, status="inactive")) == ["Naviera del Sol"]
    assert search(session, status="all").count == 4


def test_suppliers_with_the_same_name_keep_a_stable_order(session):
    first = SupplierFactory(trade_name="Hotel Central")
    second = SupplierFactory(trade_name="Hotel Central")

    assert [supplier.id for supplier in search(session).results] == [first.id, second.id]


def test_the_list_is_paginated(session):
    for _ in range(5):
        SupplierFactory()

    page = supplier_queries.list_suppliers(
        session, SupplierFilters(), PageParams(page=2, page_size=2), fake_request(query="page=2")
    )

    assert (page.count, len(page.results)) == (5, 2)
    assert "page=1" in page.previous and "page=3" in page.next


def test_a_supplier_with_two_categories_is_in_both(session, suppliers):
    assert names(search(session, category="lodging")) == ["Hotel Caribe Azul"]
    assert names(search(session, category="tours")) == [
        "Andes Tours",
        "Árbol de Pan Guías",
        "Hotel Caribe Azul",
    ]
    assert names(search(session, category="air")) == []


def test_category_and_status_filters_combine(session, suppliers):
    assert names(search(session, category="cruise")) == []
    assert names(search(session, category="cruise", status="all")) == ["Naviera del Sol"]


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("caribe hotel", ["Hotel Caribe Azul"], id="words-in-any-order"),
        pytest.param("HOTEL", ["Hotel Caribe Azul"], id="uppercase"),
        pytest.param("arbol", ["Árbol de Pan Guías"], id="without-the-accent"),
        pytest.param("costa brava", ["Hotel Caribe Azul"], id="legal-name"),
        pytest.param("azul costa", ["Hotel Caribe Azul"], id="trade-and-legal-name-together"),
    ],
)
def test_searching_by_name(session, suppliers, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("800.197", ["Hotel Caribe Azul"], id="start-of-a-nit-with-dots"),
        pytest.param("800197268-4", ["Hotel Caribe Azul"], id="whole-nit-with-a-dash"),
        pytest.param("a123", ["Andes Tours"], id="start-of-a-foreign-id"),
        pytest.param("972684", [], id="middle-of-a-number"),
    ],
)
def test_searching_by_the_start_of_the_document(session, suppliers, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("perez andrea", ["Hotel Caribe Azul"], id="contact-words-in-any-order"),
        pytest.param("lucia", ["Árbol de Pan Guías"], id="contact-without-the-accent"),
        pytest.param("andestours", ["Andes Tours"], id="part-of-the-email"),
        pytest.param("RESERVAS@", ["Hotel Caribe Azul"], id="email-in-uppercase"),
    ],
)
def test_searching_by_the_contact(session, suppliers, q, expected):
    assert names(search(session, q=q)) == expected


@pytest.mark.parametrize("q", ["%", "_", "\\", "H_tel", "H%l"])
def test_like_wildcards_are_searched_literally(session, suppliers, q):
    assert names(search(session, q=q)) == []


def test_the_list_needs_only_the_count_and_the_page(session, suppliers):
    session.expire_all()

    with recorded_statements(session) as statements:
        page = search(session)

    assert page.count == 3
    assert len(statements) == 2


def test_get_supplier_loads_who_registered_and_deactivated_it_in_the_same_query(session):
    manager = UserAccountFactory(first_name="Laura", last_name="Rojas")
    supplier = SupplierFactory(created_by=manager, inactive=True)
    # Una petición nueva empieza con la sesión vacía.
    session.expunge_all()

    with recorded_statements(session) as statements:
        found = supplier_queries.get_supplier(session, supplier.id)
        who = (found.created_by.full_name, found.deactivated_by.full_name)

    assert who == ("Laura Rojas", "Laura Rojas")
    assert len(statements) == 1


def test_get_supplier_of_an_unknown_id_is_not_found(session):
    with pytest.raises(NotFound):
        supplier_queries.get_supplier(session, 999_999_999)
