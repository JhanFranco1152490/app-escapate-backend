"""Recorrido de HU-14 (gestionar proveedores) desde la API, con los permisos reales de los
roles sembrados."""

from sqlmodel import select

from app.accounts.models import Role
from tests.accounts.helpers import signed_in
from tests.factories import UserAccountFactory
from tests.http import attach_csrf


def _seeded_role(session, name: str) -> Role:
    return session.exec(select(Role).where(Role.name == name)).one()


def test_the_supplier_manager_manages_suppliers_and_the_advisor_only_reads(
    app, session, auth_client
):
    manager = auth_client(
        user=UserAccountFactory(role=_seeded_role(session, "Encargado de proveedores"))
    )

    # CA-01: un hotel con NIT y una naviera del exterior, sin NIT y solo con correo.
    hotel = manager.post(
        "/api/suppliers",
        json={
            "trade_name": "Hotel Caribe Azul",
            "document_type": "NIT",
            "document_number": "800.197.268-4",
            "categories": ["lodging", "tours"],
            "city": "Cartagena",
            "contact_name": "Andrea Pérez",
            "contact_phone": "300 111 2233",
            "commission_rate": "10",
        },
    )
    cruise = manager.post(
        "/api/suppliers",
        json={
            "trade_name": "Naviera del Sol",
            "document_type": "FOREIGN",
            "document_number": "12-3456789",
            "categories": ["cruise"],
            "contact_name": "Julián Prieto",
            "contact_email": "julian@example.com",
        },
    )
    assert (hotel.status_code, cruise.status_code) == (201, 201)
    hotel_id, cruise_id = hotel.json()["id"], cruise.json()["id"]

    # CA-04: faltan datos obligatorios.
    incomplete = manager.post("/api/suppliers", json={"trade_name": "Transportes"})
    assert incomplete.status_code == 422
    assert {"categories", "contact_name", "contact_phone", "contact_email"} <= set(
        incomplete.json()["fields"]
    )

    # CA-05: los encuentra por nombre, por documento y por clasificación.
    def found(**params) -> list[int]:
        results = manager.get("/api/suppliers", params=params).json()["results"]
        return [item["id"] for item in results]

    assert found(q="caribe hotel") == [hotel_id]
    assert found(q="800.197") == [hotel_id]
    assert found(q="12-345") == [cruise_id]
    assert found(category="tours") == [hotel_id]

    # CA-02: la ficha trae el contacto, la clasificación y la información comercial.
    detail = manager.get(f"/api/suppliers/{hotel_id}").json()
    assert (detail["contact_name"], detail["categories"], detail["commission_rate"]) == (
        "Andrea Pérez",
        ["lodging", "tours"],
        "10.00",
    )

    # CA-03: actualiza el contacto y las condiciones de pago.
    edited = manager.put(
        f"/api/suppliers/{hotel_id}",
        json={
            "trade_name": detail["trade_name"],
            "document_type": detail["document_type"],
            "document_number": detail["document_number"],
            "categories": detail["categories"],
            "city": detail["city"],
            "contact_name": "Sofía Ramírez",
            "contact_phone": detail["contact_phone"],
            "payment_terms": "Crédito a 30 días",
            "commission_rate": detail["commission_rate"],
            "expected_version": detail["version"],
        },
    )
    assert edited.status_code == 200
    assert (edited.json()["contact_name"], edited.json()["payment_terms"]) == (
        "Sofía Ramírez",
        "Crédito a 30 días",
    )

    # La naviera se desactiva: deja de salir en la lista, y vuelve al activarla.
    off = manager.post(f"/api/suppliers/{cruise_id}/deactivate", json={"expected_version": 1})
    assert off.status_code == 200
    assert found() == [hotel_id]
    on = manager.post(f"/api/suppliers/{cruise_id}/activate", json={"expected_version": 2})
    assert on.status_code == 200
    assert set(found()) == {hotel_id, cruise_id}

    # El Asesor comercial consulta proveedores para armar cotizaciones, pero no los modifica.
    advisor = attach_csrf(
        signed_in(app, session, UserAccountFactory(role=_seeded_role(session, "Asesor comercial")))
    )
    assert advisor.get(f"/api/suppliers/{hotel_id}").status_code == 200
    assert advisor.get("/api/suppliers", params={"q": "naviera"}).json()["count"] == 1
    for method, path in [
        ("post", "/api/suppliers"),
        ("put", f"/api/suppliers/{hotel_id}"),
        ("post", f"/api/suppliers/{hotel_id}/deactivate"),
    ]:
        response = advisor.request(method, path, json={})
        assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
