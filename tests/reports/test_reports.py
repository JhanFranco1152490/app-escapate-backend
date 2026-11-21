from datetime import timedelta
from decimal import Decimal

import pytest

from app.common.dates import today
from tests.factories import QuoteFactory, QuoteItemFactory

ALL = ["reports.view", "finance.view", "sales.view", "sales.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=ALL)


def period() -> dict:
    return {
        "date_from": (today() - timedelta(days=1)).isoformat(),
        "date_to": (today() + timedelta(days=1)).isoformat(),
    }


def sold(api, destination="Cartagena") -> dict:
    quote = QuoteFactory(accepted=True, destination=destination)
    QuoteItemFactory(quote=quote, unit_cost=Decimal("1000000"), quantity=1)
    return api.post("/api/sales", json={"quote_id": quote.id}).json()


def test_the_dashboard_counts_what_needs_attention(api):
    QuoteFactory()
    QuoteFactory(sent=True, valid_until=today() - timedelta(days=1))
    sale = sold(api)

    board = api.get("/api/reports/dashboard").json()

    assert board["quotes_draft"] == 1
    assert board["quotes_expired"] == 1
    assert board["receivable"] == sale["total_price"]


def test_commercial_indicators(api):
    sold(api, "Cartagena")
    sold(api, "Cartagena")
    sold(api, "San Andrés")

    result = api.get("/api/reports/commercial", params=period()).json()

    assert (result["sales_count"], result["sales_amount"]) == (3, 3_450_000)
    assert result["average_ticket"] == 1_150_000
    assert result["conversion_percent"] == "100.00"
    assert result["top_destinations"][0] == {
        "label": "Cartagena",
        "count": 2,
        "amount": 2_300_000,
    }
    assert result["sales_by_service_type"] == [{"label": "Alojamiento", "count": 3, "amount": 0}]


def test_financial_indicators_need_the_finance_permission(api, auth_client):
    sold(api)

    result = api.get("/api/reports/financial", params=period()).json()

    assert (result["sales_amount"], result["estimated_profit"]) == (1_150_000, 150_000)
    assert result["receivable"] == 1_150_000
    # Otra sesión en el mismo cliente: reemplaza la anterior.
    no_finance = auth_client(permissions=["reports.view"])
    assert no_finance.get("/api/reports/financial", params=period()).status_code == 403


def test_a_sales_report_has_one_row_per_sale(api):
    sale = sold(api)

    report = api.get("/api/reports/sales", params=period()).json()

    assert report["columns"][0] == "Venta"
    assert [row[0] for row in report["rows"]] == [sale["code"]]


@pytest.mark.parametrize("kind", ["payments", "quotes", "expenses", "requests"])
def test_every_report_answers(api, kind):
    sold(api)

    assert api.get(f"/api/reports/{kind}", params=period()).status_code == 200


def test_the_expenses_report_needs_the_finance_permission(auth_client):
    # Los gastos operativos son datos de finanzas: ver reportes no basta, como en los
    # indicadores financieros.
    without_finance = auth_client(permissions=["reports.view"])

    assert without_finance.get("/api/reports/expenses", params=period()).status_code == 403

    with_finance = auth_client(permissions=["reports.view", "finance.view"])

    assert with_finance.get("/api/reports/expenses", params=period()).status_code == 200


def test_the_other_reports_only_need_to_view_reports(auth_client):
    viewer = auth_client(permissions=["reports.view"])

    for kind in ["sales", "payments", "quotes", "requests"]:
        assert viewer.get(f"/api/reports/{kind}", params=period()).status_code == 200


def test_the_client_history_joins_every_stage(api, auth_client):
    sale = sold(api)
    api.post(
        f"/api/sales/{sale['id']}/payments",
        json={"amount": 150_000, "paid_on": today().isoformat(), "method": "cash"},
    )
    viewer = auth_client(permissions=["clients.view"])

    history = viewer.get(f"/api/reports/clients/{sale['client']['id']}/history").json()

    assert (history["requests"], history["quotes"], history["sales"]) == (1, 1, 1)
    assert (history["total_bought"], history["total_paid"], history["balance"]) == (
        1_150_000,
        150_000,
        1_000_000,
    )
    assert {event["kind"] for event in history["events"]} == {
        "request",
        "quote",
        "sale",
        "payment",
    }
