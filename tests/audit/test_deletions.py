from decimal import Decimal

import pytest

from app.common.dates import today
from tests.factories import QuoteFactory, QuoteItemFactory

ALL = ["sales.view", "sales.manage", "finance.view", "finance.manage"]
DAY = today().isoformat()


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=ALL)


def new_sale(api) -> dict:
    quote = QuoteFactory(accepted=True)
    QuoteItemFactory(quote=quote, unit_cost=Decimal("1000000"), quantity=1)
    return api.post("/api/sales", json={"quote_id": quote.id}).json()


def pay(api, sale: dict, amount: int = 500_000) -> dict:
    return api.post(
        f"/api/sales/{sale['id']}/payments",
        json={"amount": amount, "paid_on": DAY, "method": "cash", "notes": "dato privado"},
    ).json()["payments"][-1]


def deletions(api, **params) -> list[dict]:
    response = api.get("/api/audit/deletions", params=params)
    assert response.status_code == 200, response.json()
    return response.json()["results"]


def test_removing_a_payment_leaves_who_removed_it(api):
    sale = new_sale(api)
    payment = pay(api, sale)

    api.delete(f"/api/sales/{sale['id']}/payments/{payment['id']}")

    [record] = deletions(api)
    assert (record["kind"], record["record_id"], record["sale_id"]) == (
        "client_payment",
        payment["id"],
        sale["id"],
    )
    assert (record["amount"], record["occurred_on"]) == (500_000, DAY)
    assert record["description"] == "cash"
    assert record["deleted_by"]["id"] == api.get("/api/auth/me").json()["id"]


def test_the_record_does_not_copy_free_text_that_may_hold_personal_data(api):
    sale = new_sale(api)
    payment = pay(api, sale)

    api.delete(f"/api/sales/{sale['id']}/payments/{payment['id']}")

    assert "dato privado" not in str(deletions(api))


def test_removing_a_cost_leaves_a_record(api):
    sale = new_sale(api)
    cost = api.post(
        f"/api/sales/{sale['id']}/costs",
        json={"description": "Hotel Las Américas", "amount": 400_000, "paid_on": DAY},
    ).json()["costs"][0]

    api.delete(f"/api/costs/{cost['id']}")

    [record] = deletions(api)
    assert (record["kind"], record["record_id"], record["sale_id"], record["amount"]) == (
        "actual_cost",
        cost["id"],
        sale["id"],
        400_000,
    )
    assert record["description"] == "Hotel Las Américas"


def test_removing_an_expense_leaves_a_record(api):
    expense = api.post(
        "/api/expenses",
        json={"spent_on": DAY, "category": "rent", "description": "Arriendo", "amount": 50_000},
    ).json()

    assert api.delete(f"/api/expenses/{expense['id']}").status_code == 204

    [record] = deletions(api)
    assert (record["kind"], record["record_id"], record["sale_id"]) == (
        "operating_expense",
        expense["id"],
        None,
    )
    assert (record["amount"], record["description"]) == (50_000, "Arriendo")


def test_a_removal_that_finds_nothing_leaves_no_record(api):
    assert api.delete("/api/expenses/999999").status_code == 404

    assert deletions(api) == []


def test_the_list_filters_by_kind_and_shows_the_newest_first(api):
    sale = new_sale(api)
    first, second = pay(api, sale, 100_000), pay(api, sale, 200_000)
    expense = api.post(
        "/api/expenses",
        json={"spent_on": DAY, "category": "rent", "description": "Arriendo", "amount": 50_000},
    ).json()
    api.delete(f"/api/sales/{sale['id']}/payments/{first['id']}")
    api.delete(f"/api/sales/{sale['id']}/payments/{second['id']}")
    api.delete(f"/api/expenses/{expense['id']}")

    everything = deletions(api)
    payments = deletions(api, kind="client_payment")

    assert [row["kind"] for row in everything] == [
        "operating_expense",
        "client_payment",
        "client_payment",
    ]
    assert [row["record_id"] for row in payments] == [second["id"], first["id"]]


def test_an_unknown_kind_is_rejected(api):
    assert api.get("/api/audit/deletions", params={"kind": "other"}).status_code == 422


def test_reading_the_records_needs_the_finance_permission(auth_client):
    viewer = auth_client(permissions=["sales.view", "sales.manage"])

    assert viewer.get("/api/audit/deletions").status_code == 403


def test_without_a_session_the_records_answer_401(csrf_client):
    assert csrf_client.get("/api/audit/deletions").status_code == 401
