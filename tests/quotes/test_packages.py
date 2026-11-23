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


EDITABLE = (
    "name",
    "destination",
    "description",
    "nights",
    "reference_travelers",
    "default_markup_percent",
    "exchange_rate",
    "is_active",
)


def update_body(package: dict, **changes) -> dict:
    """Lo que acepta editar un paquete: los campos editables y la versión leída."""
    body = {name: package[name] for name in EDITABLE}
    return {**body, "expected_version": package["version"], **changes}


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


def test_listing_packages_by_name_destination_and_active(api):
    caribe = new_package(api)
    cafe = new_package(api, name="Eje Cafetero", destination="Armenia")
    deactivated = api.put(f"/api/packages/{cafe['id']}", json=update_body(cafe, is_active=False))
    assert deactivated.status_code == 200, deactivated.json()

    def ids(**params) -> list[int]:
        rows = api.get("/api/packages", params=params).json()["results"]
        return [row["id"] for row in rows]

    assert ids(q="eje cafetero") == [cafe["id"]]
    assert ids(q="san andres") == [caribe["id"]]
    assert ids(active="true") == [caribe["id"]]
    assert ids(active="false") == [cafe["id"]]
    assert sorted(ids()) == sorted([caribe["id"], cafe["id"]])


def test_editing_a_package_needs_the_version_that_was_read(api):
    package = new_package(api)
    stale = api.put(
        f"/api/packages/{package['id']}",
        json=update_body(package, name="Caribe de lujo", expected_version=package["version"] + 5),
    )
    saved = api.put(
        f"/api/packages/{package['id']}", json=update_body(package, name="Caribe de lujo")
    )

    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert (saved.status_code, saved.json()["name"]) == (200, "Caribe de lujo")


def test_editing_and_removing_a_service_of_a_package(api):
    package = new_package(api)
    item = add_item(api, package)

    edited = api.put(
        f"/api/packages/{package['id']}/items/{item['id']}",
        json={
            "service_type": "lodging",
            "name": "Hotel renovado",
            "quantity": 5,
            "charge_unit": "per_night",
            "currency": "COP",
            "unit_cost": "500000",
            "expected_version": item["version"],
        },
    )
    stale = api.put(
        f"/api/packages/{package['id']}/items/{item['id']}",
        json={
            "service_type": "lodging",
            "name": "Hotel renovado",
            "quantity": 5,
            "charge_unit": "per_night",
            "currency": "COP",
            "unit_cost": "500000",
            "expected_version": item["version"],
        },
    )
    removed = api.delete(f"/api/packages/{package['id']}/items/{item['id']}")

    assert (edited.status_code, edited.json()["name"]) == (200, "Hotel renovado")
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert removed.status_code == 204
    assert api.get(f"/api/packages/{package['id']}").json()["items"] == []


def test_a_service_only_belongs_to_its_own_package(api):
    package = new_package(api)
    other = new_package(api, name="Otro paquete")
    item = add_item(api, other)

    assert api.delete(f"/api/packages/{package['id']}/items/{item['id']}").status_code == 404
    assert api.delete(f"/api/packages/{package['id']}/items/999999").status_code == 404
    assert api.get("/api/packages/999999").status_code == 404


def test_quoting_from_a_package_that_does_not_exist_is_rejected(api):
    response = api.post(
        "/api/quotes/from-package",
        json={"travel_request_id": TravelRequestFactory().id, "package_id": 999999},
    )

    assert response.status_code == 422
    assert response.json()["fields"] == {"package_id": ["El paquete no existe."]}
