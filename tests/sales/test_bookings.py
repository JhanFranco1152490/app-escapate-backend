from decimal import Decimal

from tests.factories import QuoteFactory, QuoteItemFactory, SupplierFactory

MANAGE = ["sales.view", "sales.manage"]


def test_preparing_copies_the_included_services_once(auth_client):
    api = auth_client(permissions=MANAGE)
    quote = QuoteFactory(accepted=True)
    supplier = SupplierFactory()
    QuoteItemFactory(quote=quote, name="Hotel Las Américas", supplier=supplier)
    QuoteItemFactory(quote=quote, name="Tour opcional", is_optional=True)
    sale = api.post("/api/sales", json={"quote_id": quote.id}).json()

    first = api.post(f"/api/sales/{sale['id']}/bookings/prepare").json()
    again = api.post(f"/api/sales/{sale['id']}/bookings/prepare").json()

    assert [row["name"] for row in first] == ["Hotel Las Américas"]
    assert first[0]["status"] == "to_request"
    assert first[0]["supplier"]["trade_name"] == supplier.trade_name
    assert [row["id"] for row in again] == [first[0]["id"]]


def test_confirming_a_booking(auth_client):
    api = auth_client(permissions=MANAGE)
    quote = QuoteFactory(accepted=True)
    QuoteItemFactory(quote=quote, unit_cost=Decimal("100"))
    sale = api.post("/api/sales", json={"quote_id": quote.id}).json()
    booking = api.post(f"/api/sales/{sale['id']}/bookings/prepare").json()[0]

    response = api.put(
        f"/api/bookings/{booking['id']}",
        json={"status": "confirmed", "confirmation_code": "HX-2231"},
    )

    assert (response.json()["status"], response.json()["confirmation_code"]) == (
        "confirmed",
        "HX-2231",
    )
    listed = api.get("/api/bookings", params={"status": "confirmed"}).json()["results"]
    assert [row["id"] for row in listed] == [booking["id"]]


def test_viewing_is_not_enough_to_prepare(auth_client):
    viewer = auth_client(permissions=["sales.view"])

    assert viewer.post("/api/sales/1/bookings/prepare").status_code == 403
