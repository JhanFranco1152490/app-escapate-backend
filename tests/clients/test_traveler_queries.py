import pytest

from app.clients.schemas import TravelerFilters
from app.clients.services import traveler_queries
from app.common.errors import NotFound
from app.common.pagination import PageParams
from tests.factories import ClientFactory, TravelerFactory
from tests.http import fake_request
from tests.statements import recorded_statements


def search(session, **filters):
    params = PageParams(page=1, page_size=50)
    return traveler_queries.list_travelers(
        session, TravelerFilters(**filters), params, fake_request()
    )


def names(page) -> list[str]:
    return [traveler.full_name for traveler in page.results]


@pytest.fixture
def travelers(session):
    marcela = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    empresa = ClientFactory(company=True, business_name="Viajes del Norte SAS")
    return {
        "marcela": marcela,
        "camila": TravelerFactory(
            first_name="Camila",
            last_name="Gómez Ortiz",
            document_type="TI",
            document_number="1098221334",
            reference_client=marcela,
        ),
        "julian": TravelerFactory(
            first_name="Julián",
            last_name="Gómez Prieto",
            document_type="CC",
            document_number="80112233",
            reference_client=marcela,
        ),
        "helena": TravelerFactory(
            first_name="Helena",
            last_name="Rincón Soto",
            document_type="PA",
            document_number="AT882190",
            reference_client=empresa,
        ),
        "tomas": TravelerFactory(
            first_name="Tomás", last_name="Pineda Vega", document_number="1090552118"
        ),
    }


def test_the_list_is_ordered_by_names_without_accents(session, travelers):
    assert names(search(session)) == [
        "Camila Gómez Ortiz",
        "Helena Rincón Soto",
        "Julián Gómez Prieto",
        "Tomás Pineda Vega",
    ]


@pytest.mark.parametrize(
    "q, expected",
    [
        pytest.param("gomez", ["Camila Gómez Ortiz", "Julián Gómez Prieto"], id="last-name"),
        pytest.param("ortiz camila", ["Camila Gómez Ortiz"], id="words-in-any-order"),
        pytest.param("tomas", ["Tomás Pineda Vega"], id="without-the-accent"),
        pytest.param("1.098", ["Camila Gómez Ortiz"], id="start-of-the-document"),
        pytest.param("at88", ["Helena Rincón Soto"], id="passport-in-lowercase"),
        pytest.param("2213", [], id="middle-of-the-document"),
        pytest.param("%", [], id="wildcard"),
        pytest.param("- . -", [], id="only-separators"),
    ],
)
def test_searching_by_name_or_document(session, travelers, q, expected):
    assert names(search(session, q=q)) == expected


def test_filtering_by_reference_client(session, travelers):
    page = search(session, client_id=travelers["marcela"].id)

    assert names(page) == ["Camila Gómez Ortiz", "Julián Gómez Prieto"]


def test_filtering_by_a_client_that_does_not_exist_is_an_empty_page(session, travelers):
    page = search(session, client_id=999_999_999)

    assert (page.count, page.results) == (0, [])


def test_the_list_loads_the_reference_clients_without_a_query_per_traveler(session, travelers):
    session.expire_all()
    with recorded_statements(session) as statements:
        page = search(session)
        clients = [t.reference_client and t.reference_client.display_name for t in page.results]

    assert clients == ["Marcela Gómez Ortiz", "Viajes del Norte SAS", "Marcela Gómez Ortiz", None]
    assert len(statements) == 2


def test_get_traveler_loads_its_relations_in_the_same_query(session, travelers):
    traveler_id = travelers["camila"].id
    # Una petición nueva empieza con la sesión vacía.
    session.expunge_all()
    with recorded_statements(session) as statements:
        found = traveler_queries.get_traveler(session, traveler_id)
        loaded = (
            found.reference_client.display_name,
            found.created_by.full_name,
            found.data_consent_by.full_name,
        )

    assert loaded[0] == "Marcela Gómez Ortiz"
    assert len(statements) == 1


def test_get_traveler_of_an_unknown_id_is_not_found(session):
    with pytest.raises(NotFound):
        traveler_queries.get_traveler(session, 999_999_999)
