import pytest
from pydantic import ValidationError

from app.suppliers.service_attributes import (
    ATTRIBUTE_MODELS,
    CruiseAttributes,
    FoodAttributes,
    LodgingAttributes,
    OtherAttributes,
    stored_attributes,
)
from app.suppliers.service_types import ServiceType
from tests.suppliers.samples import COMPLETE, MINIMAL


def _fields_with_errors(model, data: dict) -> set[str]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    return {".".join(str(part) for part in error["loc"]) for error in caught.value.errors()}


def test_every_service_type_has_its_attributes_model():
    assert set(ATTRIBUTE_MODELS) == set(ServiceType)


@pytest.mark.parametrize("service_type", list(ServiceType))
def test_the_minimal_attributes_of_each_type_are_valid(service_type):
    ATTRIBUTE_MODELS[service_type].model_validate(MINIMAL[service_type])


@pytest.mark.parametrize("service_type", list(ServiceType))
def test_the_complete_attributes_of_each_type_are_valid(service_type):
    ATTRIBUTE_MODELS[service_type].model_validate(COMPLETE[service_type])


@pytest.mark.parametrize(
    "service_type, field",
    [
        (ServiceType.LODGING, "lodging_kind"),
        (ServiceType.LODGING, "max_capacity"),
        (ServiceType.AIR, "origin"),
        (ServiceType.AIR, "trip_type"),
        (ServiceType.GROUND, "modality"),
        (ServiceType.TOURS, "duration_value"),
        (ServiceType.TOURS, "duration_unit"),
        (ServiceType.CRUISE, "ship_name"),
        (ServiceType.CRUISE, "departure_port"),
        (ServiceType.CRUISE, "nights"),
        (ServiceType.FOOD, "meals"),
        (ServiceType.WHOLESALER, "nights"),
    ],
)
def test_each_required_attribute_is_reported_when_missing(service_type, field):
    data = {key: value for key, value in MINIMAL[service_type].items() if key != field}

    assert _fields_with_errors(ATTRIBUTE_MODELS[service_type], data) == {field}


@pytest.mark.parametrize(
    "service_type, field",
    [
        (ServiceType.AIR, "origin"),
        (ServiceType.CRUISE, "ship_name"),
        (ServiceType.CRUISE, "departure_port"),
    ],
)
def test_a_required_text_with_only_spaces_is_missing(service_type, field):
    data = MINIMAL[service_type] | {field: "   "}

    assert _fields_with_errors(ATTRIBUTE_MODELS[service_type], data) == {field}


@pytest.mark.parametrize(
    "service_type, field, value",
    [
        (ServiceType.LODGING, "max_capacity", 0),
        (ServiceType.LODGING, "max_capacity", 51),
        (ServiceType.LODGING, "stars", 6),
        (ServiceType.AIR, "stops", 4),
        (ServiceType.AIR, "checked_bags", 6),
        (ServiceType.GROUND, "max_capacity", 61),
        (ServiceType.TOURS, "duration_value", 1000),
        (ServiceType.CRUISE, "nights", 0),
        (ServiceType.CRUISE, "nights", 61),
        (ServiceType.WHOLESALER, "nights", -1),
        (ServiceType.LODGING, "meal_plan", "spa"),
        (ServiceType.CRUISE, "itinerary", "x" * 501),
        (ServiceType.FOOD, "cuisine", "x" * 81),
    ],
)
def test_a_value_out_of_its_range_or_list_is_rejected(service_type, field, value):
    data = MINIMAL[service_type] | {field: value}

    assert _fields_with_errors(ATTRIBUTE_MODELS[service_type], data) == {field}


def test_a_field_of_another_type_is_rejected():
    data = MINIMAL[ServiceType.LODGING] | {"ship_name": "Barco de prueba"}

    assert _fields_with_errors(LodgingAttributes, data) == {"ship_name"}


def test_other_has_no_attributes_of_its_own():
    assert _fields_with_errors(OtherAttributes, {"origin": "Bogotá"}) == {"origin"}


def test_an_unknown_include_is_reported_on_the_list_not_on_its_position():
    data = MINIMAL[ServiceType.LODGING] | {"includes": ["wifi", "spa"]}

    assert _fields_with_errors(LodgingAttributes, data) == {"includes"}


def test_an_include_of_another_type_is_rejected():
    data = MINIMAL[ServiceType.LODGING] | {"includes": ["drinks_package"]}

    assert _fields_with_errors(LodgingAttributes, data) == {"includes"}


def test_a_repeated_include_is_rejected():
    data = MINIMAL[ServiceType.LODGING] | {"includes": ["wifi", "wifi"]}

    assert _fields_with_errors(LodgingAttributes, data) == {"includes"}


def test_includes_come_back_in_the_order_of_their_list():
    attributes = CruiseAttributes.model_validate(
        MINIMAL[ServiceType.CRUISE] | {"includes": ["excursions", "meals"]}
    )

    assert [include.value for include in attributes.includes] == ["meals", "excursions"]


def test_includes_may_be_empty_but_meals_may_not():
    LodgingAttributes.model_validate(MINIMAL[ServiceType.LODGING] | {"includes": []})

    assert _fields_with_errors(FoodAttributes, {"meals": []}) == {"meals"}


def test_check_in_time_does_not_take_seconds():
    data = MINIMAL[ServiceType.LODGING] | {"check_in_time": "15:00:30"}

    assert _fields_with_errors(LodgingAttributes, data) == {"check_in_time"}


def test_texts_are_trimmed():
    attributes = ATTRIBUTE_MODELS[ServiceType.AIR].model_validate(
        MINIMAL[ServiceType.AIR] | {"origin": "  Bogotá (BOG)  "}
    )

    assert attributes.origin == "Bogotá (BOG)"


def test_stored_attributes_leave_out_what_was_not_filled():
    attributes = LodgingAttributes.model_validate(
        MINIMAL[ServiceType.LODGING] | {"stars": None, "check_in_time": "15:00"}
    )

    assert stored_attributes(attributes) == {
        "lodging_kind": "hotel",
        "max_capacity": 4,
        "check_in_time": "15:00",
        "includes": [],
    }


def test_stored_attributes_keep_a_false_flag():
    attributes = ATTRIBUTE_MODELS[ServiceType.AIR].model_validate(MINIMAL[ServiceType.AIR])

    assert stored_attributes(attributes)["carry_on_included"] is False


@pytest.mark.parametrize("service_type", list(ServiceType))
def test_stored_attributes_read_back_the_same(service_type):
    model = ATTRIBUTE_MODELS[service_type]
    stored = stored_attributes(model.model_validate(COMPLETE[service_type]))

    assert stored_attributes(model.model_validate(stored)) == stored
