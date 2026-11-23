from datetime import timedelta
from decimal import Decimal

import pytest

from app.common.dates import today
from tests.factories import ClientFactory, QuoteFactory, QuoteItemFactory

MANAGE = ["sales.view", "sales.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=MANAGE)


def accepted_quote(**changes):
    quote = QuoteFactory(accepted=True, **changes)
    QuoteItemFactory(quote=quote, unit_cost=Decimal("1000000"), quantity=1)
    return quote


def sell(api, quote, **body) -> dict:
    response = api.post("/api/sales", json={"quote_id": quote.id, **body})
    assert response.status_code == 201, response.json()
    return response.json()


def pay(api, sale: dict, amount: int):
    return api.post(
        f"/api/sales/{sale['id']}/payments",
        json={"amount": amount, "paid_on": today().isoformat(), "method": "transfer"},
    )


def test_selling_an_accepted_quote_copies_its_price(api):
    quote = accepted_quote(destination="Cartagena")

    sale = sell(api, quote)

    assert sale["code"] == f"VEN-{sale['id']:04d}"
    assert (sale["total_price"], sale["total_cost"]) == (1_150_000, 1_000_000)
    assert sale["destination"] == "Cartagena"
    assert (sale["paid"], sale["balance"], sale["payment_status"]) == (0, 1_150_000, "pending")


def test_the_agreed_price_can_be_given(api):
    assert sell(api, accepted_quote(), total_price=1_300_000)["total_price"] == 1_300_000


def test_only_an_accepted_quote_is_sold_and_only_once(api):
    draft = QuoteFactory()
    quote = accepted_quote()
    sell(api, quote)

    assert api.post("/api/sales", json={"quote_id": draft.id}).json()["code"] == (
        "quote_not_accepted"
    )
    assert api.post("/api/sales", json={"quote_id": quote.id}).json()["code"] == (
        "quote_already_sold"
    )


def test_payments_lower_the_balance_and_cannot_pass_it(api):
    sale = sell(api, accepted_quote())

    partial = pay(api, sale, 500_000).json()
    too_much = pay(api, sale, 700_000)
    paid = pay(api, sale, 650_000).json()

    assert (partial["balance"], partial["payment_status"]) == (650_000, "partial")
    assert too_much.json()["fields"] == {"amount": ["El pago supera el saldo pendiente."]}
    assert (paid["balance"], paid["payment_status"]) == (0, "paid")
    assert [row["amount"] for row in paid["payments"]] == [500_000, 650_000]


def test_removing_a_payment_restores_the_balance(api):
    sale = sell(api, accepted_quote())
    payment = pay(api, sale, 500_000).json()["payments"][0]

    response = api.delete(f"/api/sales/{sale['id']}/payments/{payment['id']}")

    assert response.json()["balance"] == 1_150_000


def test_filtering_by_payment_status(api):
    pending = sell(api, accepted_quote())
    partial = sell(api, accepted_quote())
    pay(api, partial, 100)

    def ids(status: str) -> list[int]:
        rows = api.get("/api/sales", params={"payment_status": status}).json()["results"]
        return [row["id"] for row in rows]

    assert (ids("pending"), ids("partial"), ids("paid")) == ([pending["id"]], [partial["id"]], [])


def test_viewing_is_not_enough_to_register_payments(auth_client, api):
    sale = sell(api, accepted_quote())
    viewer = auth_client(permissions=["sales.view"])

    assert pay(viewer, sale, 100).status_code == 403


def test_future_date_is_allowed_for_a_scheduled_transfer(api):
    sale = sell(api, accepted_quote())
    response = api.post(
        f"/api/sales/{sale['id']}/payments",
        json={
            "amount": 100,
            "paid_on": (today() + timedelta(days=1)).isoformat(),
            "method": "cash",
        },
    )
    assert response.status_code == 201


def test_searching_by_client_destination_or_code(api):
    marta = sell(
        api,
        accepted_quote(
            client=ClientFactory(first_name="Marta", last_name="Zapatoca"),
            destination="Cartagena",
        ),
    )
    sell(api, accepted_quote(destination="Medellín"))

    def ids(text: str) -> list[int]:
        rows = api.get("/api/sales", params={"q": text}).json()["results"]
        return [row["id"] for row in rows]

    assert ids("Zapatoca") == [marta["id"]]
    assert ids("cartagena") == [marta["id"]]
    assert ids(marta["code"]) == [marta["id"]]
    assert ids("sin coincidencias") == []


def test_filtering_by_quote_and_by_client(api):
    first = sell(api, accepted_quote())
    second = sell(api, accepted_quote())

    def ids(**params) -> list[int]:
        return [row["id"] for row in api.get("/api/sales", params=params).json()["results"]]

    assert ids(quote_id=first["quote"]["id"]) == [first["id"]]
    assert ids(client_id=second["client"]["id"]) == [second["id"]]


def test_unknown_records_are_not_found(api):
    sale = sell(api, accepted_quote())
    other = sell(api, accepted_quote())
    payment = pay(api, other, 100_000).json()["payments"][0]

    assert api.get("/api/sales/999999").status_code == 404
    assert pay(api, {"id": 999999}, 1_000).status_code == 404
    assert api.delete(f"/api/sales/{sale['id']}/payments/999999").status_code == 404
    # Un pago de otra venta no se quita desde esta.
    assert api.delete(f"/api/sales/{sale['id']}/payments/{payment['id']}").status_code == 404


def test_selling_needs_a_known_quote_and_a_price(api):
    unknown = api.post("/api/sales", json={"quote_id": 999999})
    free = api.post("/api/sales", json={"quote_id": QuoteFactory(accepted=True).id})

    assert unknown.status_code == 422
    assert "quote_id" in unknown.json()["fields"]
    assert free.status_code == 422
    assert free.json()["fields"] == {"total_price": ["Indica el precio de la venta."]}
