from decimal import Decimal

import pytest

from tests.factories import (
    QuoteFactory,
    QuoteItemFactory,
    ServiceRateFactory,
    TouristServiceFactory,
)

MANAGE = ["quotes.view", "quotes.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=MANAGE)


def test_a_new_version_keeps_the_services_and_points_back(api):
    quote = QuoteFactory(sent=True)
    base = QuoteItemFactory(quote=quote, name="Hotel A")
    QuoteItemFactory(quote=quote, name="Hotel B", alternative_of_id=base.id)

    copy = api.post(f"/api/quotes/{quote.id}/copy", json={"as_new_version": True}).json()

    assert (copy["status"], copy["revision"], copy["previous_quote_id"]) == ("draft", 2, quote.id)
    names = {item["name"]: item for item in copy["items"]}
    assert names["Hotel B"]["alternative_of_id"] == names["Hotel A"]["id"]


def test_a_duplicate_starts_at_version_one(api):
    quote = QuoteFactory(revision=3)

    copy = api.post(f"/api/quotes/{quote.id}/copy", json={}).json()

    assert (copy["revision"], copy["previous_quote_id"]) == (1, None)


def test_alternatives_do_not_add_to_the_total(api):
    quote = QuoteFactory()
    base = QuoteItemFactory(quote=quote, unit_cost=Decimal("100000"), quantity=1)

    response = api.post(
        f"/api/quotes/{quote.id}/items",
        json={
            "service_type": "lodging",
            "name": "Otro hotel",
            "quantity": 1,
            "currency": "COP",
            "unit_cost": "200000",
            "alternative_of_id": base.id,
        },
    )
    detail = api.get(f"/api/quotes/{quote.id}").json()

    assert response.status_code == 201, response.json()
    assert detail["totals"]["sale"] == 115_000
    assert detail["totals"]["optional_sale"] == 0


def test_an_alternative_must_be_of_an_included_service_of_the_same_quote(api):
    quote = QuoteFactory()
    foreign = QuoteItemFactory()

    response = api.post(
        f"/api/quotes/{quote.id}/items",
        json={
            "service_type": "lodging",
            "name": "Otro hotel",
            "quantity": 1,
            "currency": "COP",
            "unit_cost": "200000",
            "alternative_of_id": foreign.id,
        },
    )

    assert list(response.json()["fields"]) == ["alternative_of_id"]


def test_the_offer_lists_active_services_with_current_rates(api):
    service = TouristServiceFactory(name="Hotel del Mar", destination="Cartagena")
    ServiceRateFactory(tourist_service=service, amount=Decimal("480000"))
    TouristServiceFactory(inactive=True, destination="Cartagena")

    rows = api.get("/api/quotes/offer", params={"q": "cartagena"}).json()["results"]

    assert [row["name"] for row in rows] == ["Hotel del Mar"]
    assert rows[0]["rates"][0]["amount"] == "480000"
    assert rows[0]["supplier"]["trade_name"] == service.supplier.trade_name
