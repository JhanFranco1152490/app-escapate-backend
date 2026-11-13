from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.suppliers.rate_schemas import ServiceRate, ServiceRateCreate, ServiceRateUpdate
from tests.factories import ServiceRateFactory

RATE = {
    "name": "Temporada alta",
    "valid_from": "2026-12-15",
    "valid_until": "2027-01-15",
    "currency": "COP",
    "charge_unit": "per_night",
    "amount": "710000",
}


def _fields_with_errors(data: dict, schema=ServiceRateCreate) -> set[str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {".".join(str(part) for part in error["loc"]) for error in caught.value.errors()}


def _messages(data: dict) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        ServiceRateCreate.model_validate(data)
    return [error["msg"] for error in caught.value.errors()]


def test_a_complete_rate_is_valid():
    rate = ServiceRateCreate.model_validate(RATE | {"conditions": "  Mínimo 5 noches.  "})

    assert rate.amount == Decimal("710000")
    assert rate.conditions == "Mínimo 5 noches."


@pytest.mark.parametrize("field", ["name", "valid_from", "currency", "charge_unit", "amount"])
def test_each_required_field_is_reported(field):
    data = {key: value for key, value in RATE.items() if key != field}

    assert _fields_with_errors(data) == {field}


def test_a_rate_without_an_end_is_valid():
    assert ServiceRateCreate.model_validate(RATE | {"valid_until": None}).valid_until is None


def test_a_rate_may_end_the_day_it_starts():
    data = RATE | {"valid_until": RATE["valid_from"]}

    assert ServiceRateCreate.model_validate(data).valid_until == date(2026, 12, 15)


def test_a_rate_that_ends_before_it_starts_is_reported_on_its_end():
    data = RATE | {"valid_until": "2026-12-14"}

    assert _fields_with_errors(data) == {"valid_until"}
    assert _messages(data) == ["La fecha final no puede ser anterior a la inicial."]


@pytest.mark.parametrize("amount", ["0", "-1", "1250.505", "1000000000000"])
def test_an_amount_out_of_range_is_rejected(amount):
    assert _fields_with_errors(RATE | {"currency": "USD", "amount": amount}) == {"amount"}


def test_pesos_do_not_take_cents():
    data = RATE | {"amount": "710000.50"}

    assert _fields_with_errors(data) == {"amount"}
    assert _messages(data) == ["En pesos el valor va sin decimales."]


def test_pesos_written_with_zero_cents_are_whole():
    assert ServiceRateCreate.model_validate(RATE | {"amount": "710000.00"}).amount == 710000


def test_dollars_take_up_to_two_decimals():
    rate = ServiceRateCreate.model_validate(RATE | {"currency": "USD", "amount": "1250.5"})

    assert rate.amount == Decimal("1250.5")


def test_an_unknown_currency_is_reported_only_once():
    assert _fields_with_errors(RATE | {"currency": "EUR", "amount": "10.5"}) == {"currency"}


def test_unknown_fields_are_rejected():
    assert _fields_with_errors(RATE | {"tourist_service_id": 1}) == {"tourist_service_id"}


def test_the_update_needs_the_expected_version():
    assert _fields_with_errors(RATE, ServiceRateUpdate) == {"expected_version"}


def test_the_output_writes_pesos_without_decimals_and_dollars_with_two(session):
    pesos = ServiceRateFactory(amount=Decimal("710000"))
    dollars = ServiceRateFactory(currency="USD", charge_unit="per_night", amount=Decimal("1250.5"))
    session.expire_all()

    assert ServiceRate.model_validate(pesos).model_dump(mode="json")["amount"] == "710000"
    assert ServiceRate.model_validate(dollars).model_dump(mode="json")["amount"] == "1250.50"


def test_the_output_carries_the_validity_and_who_registered_it(session):
    rate = ServiceRateFactory(valid_from=date(2020, 1, 1), valid_until=date(2020, 12, 31))

    dumped = ServiceRate.model_validate(rate).model_dump(mode="json")

    assert dumped["validity_status"] == "expired"
    assert dumped["created_by"]["id"] == rate.created_by_id
    assert set(dumped) == {
        "id",
        "name",
        "valid_from",
        "valid_until",
        "currency",
        "charge_unit",
        "amount",
        "conditions",
        "validity_status",
        "created_by",
        "created_at",
        "updated_at",
        "version",
    }


def test_the_amount_is_a_string_in_the_api_schema():
    schema = ServiceRate.model_json_schema(mode="serialization")

    assert schema["properties"]["amount"]["type"] == "string"
