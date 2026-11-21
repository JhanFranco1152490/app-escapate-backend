"""Borrador de alternativas: opciones de un servicio por nivel de calidad y elegir cuál pasa a
la cotización."""

from decimal import Decimal

import pytest

from tests.factories import QuoteFactory, QuoteItemFactory

MANAGE = ["quotes.view", "quotes.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=MANAGE)


def item_body(**fields):
    return {
        "service_type": "lodging",
        "name": "Hotel superior",
        "quantity": 2,
        "charge_unit": "per_night",
        "currency": "COP",
        "unit_cost": "600000",
        **fields,
    }


def by_name(quote: dict) -> dict:
    return {item["name"]: item for item in quote["items"]}


def test_an_option_keeps_its_quality_level(api):
    quote = QuoteFactory()
    base = QuoteItemFactory(quote=quote, name="Hotel económico", quality_level="economy")

    response = api.post(
        f"/api/quotes/{quote.id}/items",
        json=item_body(alternative_of_id=base.id, quality_level="superior"),
    )

    assert response.status_code == 201
    assert response.json()["quality_level"] == "superior"


def test_an_unknown_quality_level_is_a_field_error(api):
    quote = QuoteFactory()

    response = api.post(f"/api/quotes/{quote.id}/items", json=item_body(quality_level="gold"))

    assert response.status_code == 422
    assert list(response.json()["fields"]) == ["quality_level"]


def test_choosing_an_alternative_swaps_it_with_the_included_service(api):
    quote = QuoteFactory()
    base = QuoteItemFactory(quote=quote, name="Hotel A", unit_cost=Decimal("400000"))
    chosen = QuoteItemFactory(
        quote=quote, name="Hotel B", alternative_of_id=base.id, unit_cost=Decimal("600000")
    )
    QuoteItemFactory(quote=quote, name="Hotel C", alternative_of_id=base.id)
    before = api.get(f"/api/quotes/{quote.id}").json()["totals"]["cost"]

    response = api.post(f"/api/quotes/{quote.id}/items/{chosen.id}/choose")

    assert response.status_code == 200
    items = by_name(response.json())
    assert items["Hotel B"]["alternative_of_id"] is None
    assert items["Hotel A"]["alternative_of_id"] == chosen.id
    assert items["Hotel C"]["alternative_of_id"] == chosen.id
    # El total pasa a contar la elegida (2 noches a 600.000 en vez de a 400.000).
    assert response.json()["totals"]["cost"] == before + 400_000


def test_an_included_service_cannot_be_chosen(api):
    quote = QuoteFactory()
    base = QuoteItemFactory(quote=quote)

    response = api.post(f"/api/quotes/{quote.id}/items/{base.id}/choose")

    assert (response.status_code, response.json()["code"]) == (409, "not_an_alternative")


def test_only_a_draft_changes_its_choice(api):
    quote = QuoteFactory(sent=True)
    base = QuoteItemFactory(quote=quote)
    alternative = QuoteItemFactory(quote=quote, alternative_of_id=base.id)

    response = api.post(f"/api/quotes/{quote.id}/items/{alternative.id}/choose")

    assert (response.status_code, response.json()["code"]) == (409, "quote_not_editable")


def test_an_item_of_another_quote_is_not_found(api):
    other = QuoteItemFactory()
    alternative = QuoteItemFactory(quote=other.quote, alternative_of_id=other.id)

    response = api.post(f"/api/quotes/{QuoteFactory().id}/items/{alternative.id}/choose")

    assert response.status_code == 404


def test_copies_and_packages_keep_the_quality_level(api):
    quote = QuoteFactory()
    QuoteItemFactory(quote=quote, name="Hotel A", quality_level="luxury")

    copy = api.post(f"/api/quotes/{quote.id}/copy", json={}).json()

    assert by_name(copy)["Hotel A"]["quality_level"] == "luxury"
