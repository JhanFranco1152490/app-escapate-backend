from datetime import date, datetime, timedelta, timezone

import pytest

from app.common.errors import NotFound
from app.common.pagination import PageParams
from app.travel_requests import models
from app.travel_requests.schemas import SummaryFilters, TravelRequestFilters
from app.travel_requests.services import request_queries
from tests.factories import ClientFactory, TravelRequestFactory, UserAccountFactory
from tests.http import fake_request
from tests.statements import recorded_statements

TODAY = date(2026, 11, 13)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(models, "today", lambda: TODAY)
    monkeypatch.setattr(request_queries, "today", lambda: TODAY)


def _days_ago(days: int, hour_utc: int = 15) -> datetime:
    day = TODAY - timedelta(days=days)
    return datetime(day.year, day.month, day.day, hour_utc, tzinfo=timezone.utc)


def search(session, **filters):
    params = PageParams(page=1, page_size=50)
    return request_queries.list_requests(
        session, TravelRequestFilters(**filters), params, fake_request()
    )


def ids(page) -> list[int]:
    return [request.id for request in page.results]


@pytest.fixture
def requests(session):
    marcela = ClientFactory(
        first_name="Marcela", last_name="Gómez Ortiz", document_number="1020304050"
    )
    tomas = ClientFactory(first_name="Tomás", last_name="Pineda Vega", document_number="80112233")
    return {
        "san_andres": TravelRequestFactory(client=marcela, destination="San Andrés"),
        "cartagena": TravelRequestFactory(client=tomas, destination="Cartagena y Santa Marta"),
        "cancun": TravelRequestFactory(client=marcela, destination="Cancún", flexible=True),
    }


def test_without_filters_the_most_recently_changed_come_first(session, requests):
    # Dentro de la transacción de la prueba now() no avanza: las horas se fijan a mano.
    requests["san_andres"].updated_at = _days_ago(2)
    requests["cartagena"].updated_at = _days_ago(0)
    requests["cancun"].updated_at = _days_ago(5)
    session.flush()

    page = search(session)

    assert ids(page) == [
        requests["cartagena"].id,
        requests["san_andres"].id,
        requests["cancun"].id,
    ]


@pytest.mark.parametrize("written", ["SOL-{id:04d}", "sol-{id}", "{id}", "0{id}"])
def test_search_by_code(session, requests, written):
    target = requests["cartagena"]

    assert ids(search(session, q=written.format(id=target.id))) == [target.id]


def test_search_by_client_name_without_accents_in_any_order(session, requests):
    found = ids(search(session, q="gomez marcela"))

    assert set(found) == {requests["san_andres"].id, requests["cancun"].id}


def test_search_by_the_start_of_the_client_document_with_dots(session, requests):
    assert ids(search(session, q="80.112")) == [requests["cartagena"].id]


def test_search_by_every_word_of_the_destination(session, requests):
    assert ids(search(session, q="santa cartagena")) == [requests["cartagena"].id]
    assert ids(search(session, q="cancun")) == [requests["cancun"].id]


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_like_wildcards_are_searched_literally(session, requests, wildcard):
    assert ids(search(session, q=wildcard)) == []


def test_filter_by_status_and_pending(session, requests):
    quoting = TravelRequestFactory(status="quoting")
    quoted = TravelRequestFactory(status="quoted")
    closed = TravelRequestFactory(closed=True)

    pending = set(ids(search(session, status="pending")))

    assert ids(search(session, status="quoted")) == [quoted.id]
    assert ids(search(session, status="closed")) == [closed.id]
    assert quoting.id in pending and requests["san_andres"].id in pending
    assert not {quoted.id, closed.id} & pending


def test_filter_by_advisor_and_by_client(session, requests):
    other_advisor = UserAccountFactory()
    reassigned = TravelRequestFactory(assigned_to=other_advisor)
    marcela = requests["san_andres"].client

    assert ids(search(session, assigned_to=other_advisor.id)) == [reassigned.id]
    assert set(ids(search(session, client_id=marcela.id))) == {
        requests["san_andres"].id,
        requests["cancun"].id,
    }


def test_filters_on_records_that_do_not_exist_give_an_empty_page(session, requests):
    assert search(session, assigned_to=999_999_999).count == 0
    assert search(session, client_id=999_999_999).count == 0


def test_oldest_first_puts_the_longest_waiting_on_top(session):
    newest = TravelRequestFactory(created_at=_days_ago(0))
    oldest = TravelRequestFactory(created_at=_days_ago(6))
    middle = TravelRequestFactory(created_at=_days_ago(2))

    page = search(session, status="pending", sort="oldest")

    assert ids(page) == [oldest.id, middle.id, newest.id]


def test_the_list_loads_client_and_advisor_in_one_query(session, requests):
    session.expunge_all()

    with recorded_statements(session) as statements:
        page = search(session)
        for request in page.results:
            assert request.client.display_name
            assert request.assigned_to.full_name

    # Una para contar y otra para las filas, con cliente y asesor en la misma.
    assert len(statements) == 2


def test_get_brings_the_request_with_everything_it_shows(session):
    request = TravelRequestFactory(closed=True)
    session.expunge_all()

    found = request_queries.get_request(session, request.id)

    assert found.id == request.id
    assert found.closed_by is not None
    assert found.created_by is not None


def test_get_an_unknown_request_is_not_found(session):
    with pytest.raises(NotFound):
        request_queries.get_request(session, 999_999_999)


def test_the_summary_counts_by_status_and_pending(session):
    advisor = UserAccountFactory()
    TravelRequestFactory(assigned_to=advisor, created_at=_days_ago(3))
    TravelRequestFactory(assigned_to=advisor, created_at=_days_ago(4))
    TravelRequestFactory(assigned_to=advisor, status="quoting", created_at=_days_ago(10))
    TravelRequestFactory(assigned_to=advisor, status="quoted", created_at=_days_ago(10))
    TravelRequestFactory(assigned_to=advisor, closed=True, created_at=_days_ago(10))
    TravelRequestFactory(created_at=_days_ago(10))

    summary = request_queries.request_summary(session, SummaryFilters(assigned_to=advisor.id))

    assert summary.by_status.model_dump() == {"new": 2, "quoting": 1, "quoted": 1, "closed": 1}
    assert summary.total == 5
    assert summary.pending == 3
    # La de hace 3 días no cuenta; la de hace 4 y la que está en cotización hace 10, sí.
    assert summary.pending_over_3_days == 2


def test_the_summary_counts_the_wait_in_bogota_days(session):
    client = ClientFactory()
    # 23:00 de hace cuatro días en Bogotá son las 04:00 de hace tres días en UTC.
    TravelRequestFactory(client=client, created_at=_days_ago(3, hour_utc=4))

    summary = request_queries.request_summary(session, SummaryFilters(client_id=client.id))

    assert summary.pending_over_3_days == 1


def test_the_summary_of_a_client_without_requests_is_all_zero(session):
    summary = request_queries.request_summary(session, SummaryFilters(client_id=999_999_999))

    assert summary.total == 0
    assert summary.by_status.model_dump() == {"new": 0, "quoting": 0, "quoted": 0, "closed": 0}
