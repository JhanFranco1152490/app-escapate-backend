"""Recorrido de HU-15 (servicios turísticos) y HU-16 (tarifas) desde la API, con los permisos
reales de los roles sembrados."""

from datetime import date

from sqlmodel import select

from app.accounts.models import Role
from app.suppliers import tourist_service_models
from app.suppliers.services import rate_queries, tourist_service_queries
from tests.accounts.helpers import signed_in
from tests.factories import SupplierFactory, UserAccountFactory
from tests.http import attach_csrf


def _seeded_role(session, name: str) -> Role:
    return session.exec(select(Role).where(Role.name == name)).one()


def _rate(name: str, valid_from: str, valid_until: str | None, amount: str, **extra) -> dict:
    return {
        "name": name,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "currency": "COP",
        "charge_unit": "per_night",
        "amount": amount,
    } | extra


def test_the_supplier_manager_manages_services_and_rates_and_the_advisor_only_reads(
    app, session, auth_client, monkeypatch
):
    for module in (tourist_service_queries, rate_queries, tourist_service_models):
        monkeypatch.setattr(module, "today", lambda: date(2026, 11, 7))
    supplier = SupplierFactory(trade_name="Hotel Caribe Azul", categories=["lodging", "tours"])
    manager = auth_client(
        user=UserAccountFactory(role=_seeded_role(session, "Encargado de proveedores"))
    )
    services_path = f"/api/suppliers/{supplier.id}/tourist-services"

    # HU-15 CA-01 a CA-03: un alojamiento y un tour, cada uno con sus campos, del proveedor.
    room = manager.post(
        services_path,
        json={
            "service_type": "lodging",
            "name": "Habitación familiar conectada",
            "destination": "Cartagena",
            "conditions": "Cancelación sin costo hasta 30 días antes.",
            "attributes": {"lodging_kind": "hotel", "meal_plan": "breakfast", "max_capacity": 4},
        },
    )
    tour = manager.post(
        services_path,
        json={
            "service_type": "tours",
            "name": "Islas del Rosario",
            "destination": "Cartagena",
            "attributes": {"duration_value": 8, "duration_unit": "hours", "includes": ["guide"]},
        },
    )
    assert (room.status_code, tour.status_code) == (201, 201)
    room_id = room.json()["id"]
    assert room.json()["supplier"]["id"] == supplier.id

    # HU-15 CA-06: un tipo que el proveedor no vende y un servicio sin sus datos obligatorios.
    cruise = manager.post(
        services_path,
        json={
            "service_type": "cruise",
            "name": "Caribe occidental",
            "destination": "Caribe",
            "attributes": {"ship_name": "Barco de prueba", "departure_port": "Miami", "nights": 7},
        },
    )
    assert list(cruise.json()["fields"]) == ["service_type"]
    incomplete = manager.post(
        services_path, json={"service_type": "lodging", "name": "Suite", "attributes": {}}
    )
    assert incomplete.status_code == 422
    assert {"destination", "attributes.lodging_kind", "attributes.max_capacity"} <= set(
        incomplete.json()["fields"]
    )

    # HU-15 CA-04: la ficha trae sus características y condiciones.
    detail = manager.get(f"/api/tourist-services/{room_id}").json()
    assert (detail["attributes"]["meal_plan"], detail["conditions"]) == (
        "breakfast",
        "Cancelación sin costo hasta 30 días antes.",
    )

    # HU-15 CA-05: se corrige la capacidad.
    edited = manager.put(
        f"/api/tourist-services/{room_id}",
        json={
            "service_type": "lodging",
            "name": detail["name"],
            "destination": detail["destination"],
            "conditions": detail["conditions"],
            "attributes": {"lodging_kind": "hotel", "meal_plan": "breakfast", "max_capacity": 5},
            "expected_version": detail["version"],
        },
    )
    assert (edited.status_code, edited.json()["attributes"]["max_capacity"]) == (200, 5)

    # HU-16 CA-01 y CA-02: tres temporadas en pesos y una en dólares, con sus condiciones.
    rates_path = f"/api/tourist-services/{room_id}/rates"
    created = [
        manager.post(rates_path, json=body)
        for body in (
            _rate(
                "Temporada alta", "2026-12-15", "2027-01-15", "710000", conditions="Mín. 5 noches."
            ),
            _rate("Temporada media", "2027-01-16", "2027-06-30", "560000"),
            _rate("Temporada baja", "2026-07-01", "2026-12-14", "480000"),
            _rate("Tarifa en dólares", "2026-11-01", None, "189.90", currency="USD"),
        )
    ]
    assert [response.status_code for response in created] == [201] * 4
    high = created[0].json()
    assert high["conditions"] == "Mín. 5 noches."

    # HU-16 CA-05: una tarifa sin valor no se guarda.
    no_value = manager.post(rates_path, json=_rate("Sin valor", "2026-12-01", None, "0"))
    assert list(no_value.json()["fields"]) == ["amount"]

    # HU-16 CA-03: cambia el valor de la temporada alta.
    updated = manager.put(
        f"{rates_path}/{high['id']}",
        json=_rate("Temporada alta", "2026-12-15", "2027-01-15", "760000", expected_version=1),
    )
    assert (updated.status_code, updated.json()["amount"]) == (200, "760000")

    # HU-16 CA-04: las tarifas se distinguen por nombre, vigencia y estado.
    listed = manager.get(rates_path).json()["results"]
    assert [(rate["name"], rate["validity_status"]) for rate in listed] == [
        ("Temporada baja", "current"),
        ("Tarifa en dólares", "current"),
        ("Temporada alta", "upcoming"),
        ("Temporada media", "upcoming"),
    ]
    assert manager.get(f"/api/tourist-services/{room_id}").json()["current_rate_count"] == 2

    # Una tarifa mal cargada se borra.
    dollars_id = created[3].json()["id"]
    deleted = manager.delete(f"{rates_path}/{dollars_id}", params={"expected_version": 1})
    assert deleted.status_code == 204
    assert manager.get(rates_path).json()["count"] == 3

    # El servicio se desactiva, no recibe tarifas nuevas, y vuelve al activarlo.
    off = manager.post(f"/api/tourist-services/{room_id}/deactivate", json={"expected_version": 2})
    assert off.status_code == 200
    blocked = manager.post(rates_path, json=_rate("Nueva", "2027-07-01", None, "500000"))
    assert blocked.json()["code"] == "service_inactive"
    on = manager.post(f"/api/tourist-services/{room_id}/activate", json={"expected_version": 3})
    assert on.json()["is_active"]
    supplier_row = manager.get("/api/suppliers", params={"q": "caribe"}).json()["results"][0]
    assert supplier_row["active_service_count"] == 2

    # El Asesor comercial consulta servicios y tarifas para cotizar, pero no los modifica.
    advisor = attach_csrf(
        signed_in(app, session, UserAccountFactory(role=_seeded_role(session, "Asesor comercial")))
    )
    assert advisor.get(f"/api/tourist-services/{room_id}").status_code == 200
    assert advisor.get(rates_path).json()["count"] == 3
    for method, path in [
        ("post", services_path),
        ("put", f"/api/tourist-services/{room_id}"),
        ("post", f"/api/tourist-services/{room_id}/deactivate"),
        ("post", rates_path),
        ("put", f"{rates_path}/{high['id']}"),
    ]:
        response = advisor.request(method, path, json={})
        assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
