from datetime import timedelta
from decimal import Decimal

import pytest

from app.common.dates import today
from tests.factories import QuoteFactory, QuoteItemFactory

ALL = ["sales.view", "sales.manage", "finance.view", "finance.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=ALL)


def new_sale(api) -> dict:
    quote = QuoteFactory(accepted=True)
    QuoteItemFactory(quote=quote, unit_cost=Decimal("1000000"), quantity=1)
    return api.post("/api/sales", json={"quote_id": quote.id}).json()


def test_profitability_uses_the_estimate_until_there_are_actual_costs(api):
    sale = new_sale(api)

    before = api.get(f"/api/sales/{sale['id']}/profitability").json()
    after = api.post(
        f"/api/sales/{sale['id']}/costs",
        json={"description": "Hotel", "amount": 1_050_000, "paid_on": today().isoformat()},
    ).json()

    assert (before["profit"], before["uses_actual_cost"]) == (150_000, False)
    assert after["profit"] == 100_000
    assert after["margin_percent"] == "8.70"
    assert after["cost_difference"] == 50_000
    assert (after["paid_to_suppliers"], after["owed_to_suppliers"]) == (1_050_000, 0)


def test_an_unpaid_cost_is_owed_to_the_supplier(api):
    sale = new_sale(api)

    result = api.post(
        f"/api/sales/{sale['id']}/costs", json={"description": "Traslado", "amount": 80_000}
    ).json()

    assert result["owed_to_suppliers"] == 80_000


def test_the_summary_adds_income_and_expenses_by_month(api):
    sale = new_sale(api)
    day = today().isoformat()
    api.post(
        f"/api/sales/{sale['id']}/payments",
        json={"amount": 600_000, "paid_on": day, "method": "transfer"},
    )
    api.post(
        f"/api/sales/{sale['id']}/costs",
        json={"description": "Hotel", "amount": 400_000, "paid_on": day},
    )
    api.post(
        "/api/expenses",
        json={"spent_on": day, "category": "rent", "description": "Arriendo", "amount": 50_000},
    )

    period = {
        "date_from": (today() - timedelta(days=1)).isoformat(),
        "date_to": (today() + timedelta(days=1)).isoformat(),
    }
    summary = api.get("/api/finance/summary", params=period).json()

    assert (summary["income"], summary["expenses"], summary["net"]) == (600_000, 450_000, 150_000)
    assert summary["by_category"]["rent"] == 50_000
    assert sum(row["net"] for row in summary["by_month"]) == 150_000
    listed = api.get("/api/expenses", params=period).json()["results"]
    assert [row["description"] for row in listed] == ["Arriendo"]


def test_finance_needs_its_own_permission(auth_client):
    viewer = auth_client(permissions=["sales.view"])

    response = viewer.get(
        "/api/finance/summary", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )

    assert response.status_code == 403


def add_cost(api, sale: dict, **body) -> dict:
    response = api.post(
        f"/api/sales/{sale['id']}/costs",
        json={"description": "Hotel", "amount": 1_050_000, **body},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_editing_a_cost_changes_the_profit(api):
    sale = new_sale(api)
    cost = add_cost(api, sale)["costs"][0]

    result = api.put(
        f"/api/costs/{cost['id']}",
        json={
            "description": "Hotel y traslado",
            "amount": 900_000,
            "paid_on": today().isoformat(),
        },
    ).json()

    assert (result["profit"], result["paid_to_suppliers"]) == (250_000, 900_000)
    assert [row["description"] for row in result["costs"]] == ["Hotel y traslado"]


def test_removing_the_only_cost_goes_back_to_the_estimate(api):
    sale = new_sale(api)
    cost = add_cost(api, sale)["costs"][0]

    result = api.delete(f"/api/costs/{cost['id']}").json()

    assert (result["uses_actual_cost"], result["profit"], result["costs"]) == (False, 150_000, [])


def test_a_cost_needs_a_supplier_that_exists(api):
    sale = new_sale(api)
    cost = add_cost(api, sale)["costs"][0]

    created = api.post(
        f"/api/sales/{sale['id']}/costs",
        json={"description": "Hotel", "amount": 1_000, "supplier_id": 999999},
    )
    edited = api.put(
        f"/api/costs/{cost['id']}",
        json={"description": "Hotel", "amount": 1_000, "supplier_id": 999999},
    )

    for response in (created, edited):
        assert response.status_code == 422
        assert response.json()["fields"] == {"supplier_id": ["El proveedor no existe."]}


def test_unknown_sale_or_cost_is_not_found(api):
    body = {"description": "Hotel", "amount": 1_000}

    assert api.get("/api/sales/999999/profitability").status_code == 404
    assert api.post("/api/sales/999999/costs", json=body).status_code == 404
    assert api.put("/api/costs/999999", json=body).status_code == 404
    assert api.delete("/api/costs/999999").status_code == 404
