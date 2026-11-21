import pytest

from tests.factories import TravelRequestFactory

MANAGE = ["quotes.view", "quotes.manage"]


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=MANAGE)


def new_package(api, **changes) -> dict:
    response = api.post(
        "/api/packages",
        json={
            "name": "Caribe en familia",
            "destination": "San Andrés",
            "nights": 5,
            "reference_travelers": 2,
            **changes,
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def add_item(api, package: dict, **changes) -> dict:
    response = api.post(
        f"/api/packages/{package['id']}/items",
        json={
            "service_type": "lodging",
            "name": "Hotel frente al mar",
            "quantity": 5,
            "charge_unit": "per_night",
            "currency": "COP",
            "unit_cost": "400000",
            **changes,
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_a_package_prices_its_services(api):
    package = new_package(api)
    add_item(api, package)
    add_item(api, package, name="Tour opcional", is_optional=True, quantity=2, unit_cost="50000")

    detail = api.get(f"/api/packages/{package['id']}").json()

    assert detail["code"] == f"PAQ-{package['id']:04d}"
    assert detail["totals"]["sale"] == 2_300_000
    assert detail["totals"]["per_person"] == 1_150_000
    assert detail["totals"]["optional_sale"] == 115_000


def test_a_package_has_no_alternatives(api):
    package = new_package(api)
    item = add_item(api, package)

    response = api.post(
        f"/api/packages/{package['id']}/items",
        json={
            "service_type": "lodging",
            "name": "Otro hotel",
            "quantity": 1,
            "currency": "COP",
            "unit_cost": "1",
            "alternative_of_id": item["id"],
        },
    )

    assert list(response.json()["fields"]) == ["alternative_of_id"]


def test_quoting_from_a_package_copies_it_without_changing_it(api, session):
    package = new_package(api, default_markup_percent="20")
    add_item(api, package)
    request = TravelRequestFactory()

    quote = api.post(
        "/api/quotes/from-package",
        json={"travel_request_id": request.id, "package_id": package["id"]},
    )

    assert quote.status_code == 201, quote.json()
    body = quote.json()
    assert body["travel_request"]["id"] == request.id
    assert [item["name"] for item in body["items"]] == ["Hotel frente al mar"]
    assert body["default_markup_percent"] == "20.00"
    assert package["code"] in body["notes"]
    session.refresh(request)
    assert request.status == "quoted"
    unchanged = api.get(f"/api/packages/{package['id']}").json()
    assert len(unchanged["items"]) == 1


def test_an_inactive_package_is_not_quoted(api):
    package = new_package(api, is_active=False)

    response = api.post(
        "/api/quotes/from-package",
        json={"travel_request_id": TravelRequestFactory().id, "package_id": package["id"]},
    )

    assert list(response.json()["fields"]) == ["package_id"]
