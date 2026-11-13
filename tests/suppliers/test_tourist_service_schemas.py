from datetime import datetime, timezone

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.suppliers.schemas import SupplierDetail, SupplierListItem
from app.suppliers.service_attributes import AirAttributes, LodgingAttributes
from app.suppliers.tourist_service_models import TouristService
from app.suppliers.tourist_service_schemas import (
    TouristServiceCreate,
    TouristServiceDetail,
    TouristServiceListItem,
    TouristServiceUpdate,
)
from tests.http import attach_csrf

LODGING = {
    "service_type": "lodging",
    "name": "Habitación familiar",
    "destination": "Cartagena",
    "attributes": {"lodging_kind": "hotel", "max_capacity": 4},
}


def _fields_with_errors(data: dict, schema=TouristServiceCreate) -> set[str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {".".join(str(part) for part in error["loc"]) for error in caught.value.errors()}


def test_the_attributes_are_validated_with_the_model_of_the_type():
    service = TouristServiceCreate.model_validate(LODGING)

    assert isinstance(service.attributes, LodgingAttributes)
    assert service.attributes.max_capacity == 4


def test_the_same_attributes_are_wrong_for_another_type():
    data = LODGING | {"service_type": "air"}

    assert _fields_with_errors(data) == {
        "attributes.origin",
        "attributes.trip_type",
        "attributes.lodging_kind",
        "attributes.max_capacity",
    }


def test_missing_attributes_are_validated_as_an_empty_object():
    data = {key: value for key, value in LODGING.items() if key != "attributes"}

    assert _fields_with_errors(data) == {"attributes.lodging_kind", "attributes.max_capacity"}


def test_a_type_without_attributes_of_its_own_needs_none():
    service = TouristServiceCreate.model_validate(
        LODGING | {"service_type": "other", "attributes": {}}
    )

    assert service.attributes.model_dump() == {}


@pytest.mark.parametrize("field", ["service_type", "name", "destination"])
def test_each_common_required_field_is_reported(field):
    data = {key: value for key, value in LODGING.items() if key != field}

    assert field in _fields_with_errors(data)


@pytest.mark.parametrize("field", ["name", "destination"])
def test_a_common_text_with_only_spaces_is_missing(field):
    assert _fields_with_errors(LODGING | {field: "   "}) == {field}


def test_an_unknown_type_reports_only_the_type():
    data = LODGING | {"service_type": "spa", "attributes": {"anything": 1}}

    assert _fields_with_errors(data) == {"service_type"}


def test_attributes_that_are_not_an_object_are_rejected():
    assert _fields_with_errors(LODGING | {"attributes": ["hotel"]}) == {"attributes"}


def test_errors_of_the_body_and_of_the_attributes_come_together():
    data = LODGING | {"name": "", "supplier_id": 1, "attributes": {"lodging_kind": "spa"}}

    assert _fields_with_errors(data) == {
        "name",
        "supplier_id",
        "attributes.lodging_kind",
        "attributes.max_capacity",
    }


def test_long_texts_have_their_limit():
    data = LODGING | {"description": "x" * 2001, "conditions": "x" * 2001}

    assert _fields_with_errors(data) == {"description", "conditions"}


def test_the_update_needs_the_expected_version():
    assert _fields_with_errors(LODGING, TouristServiceUpdate) == {"expected_version"}
    assert (
        TouristServiceUpdate.model_validate(LODGING | {"expected_version": 3}).expected_version
        == 3
    )


def test_the_update_validates_the_attributes_too():
    data = LODGING | {"expected_version": 1, "attributes": {"lodging_kind": "hotel"}}

    assert _fields_with_errors(data, TouristServiceUpdate) == {"attributes.max_capacity"}


def test_the_api_reports_each_attribute_by_its_path():
    router = APIRouter()

    @router.post("/api/test/services")
    def create(data: TouristServiceCreate) -> dict:
        return {}

    app = create_app(Settings(secret_key="x" * 32))
    app.include_router(router)
    client = attach_csrf(TestClient(app, base_url="https://testserver"))

    response = client.post(
        "/api/test/services", json=LODGING | {"name": "", "attributes": {"lodging_kind": "hotel"}}
    )

    assert response.status_code == 422
    assert set(response.json()["fields"]) == {"name", "attributes.max_capacity"}


def _service(**overrides) -> TouristService:
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    values = {
        "id": 1,
        "supplier_id": 1,
        "service_type": "air",
        "name": "Bogotá – Cartagena",
        "destination": "Cartagena",
        "attributes": {
            "origin": "Bogotá (BOG)",
            "trip_type": "round_trip",
            "carry_on_included": False,
        },
        "is_active": True,
        "created_by_id": 1,
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
    return TouristService(**(values | overrides))


def test_the_list_item_carries_the_count_of_current_rates():
    item = TouristServiceListItem.from_service(_service(), current_rate_count=2)

    assert item.current_rate_count == 2
    assert item.model_dump(mode="json") == {
        "id": 1,
        "service_type": "air",
        "name": "Bogotá – Cartagena",
        "destination": "Cartagena",
        "is_active": True,
        "current_rate_count": 2,
    }


def test_the_detail_reads_the_attributes_with_the_model_of_its_type(session):
    from tests.factories import SupplierFactory

    supplier = SupplierFactory(categories=["air"])
    service = _service(supplier=supplier, created_by=supplier.created_by)

    detail = TouristServiceDetail.from_service(service, current_rate_count=0)

    assert isinstance(detail.attributes, AirAttributes)
    dumped = detail.model_dump(mode="json")
    assert dumped["attributes"]["origin"] == "Bogotá (BOG)"
    assert dumped["attributes"]["cabin_class"] is None
    assert dumped["supplier"] == {
        "id": supplier.id,
        "trade_name": supplier.trade_name,
        "is_active": True,
    }


def test_the_supplier_list_counts_its_services_but_the_detail_does_not():
    assert "active_service_count" in SupplierListItem.model_fields
    assert "active_service_count" not in SupplierDetail.model_fields
