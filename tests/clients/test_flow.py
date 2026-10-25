"""Recorrido de HU-06 (gestionar clientes) y HU-08 (gestionar viajeros) desde la API, con los
permisos reales de los roles sembrados."""

from sqlmodel import select

from app.accounts.models import Role
from tests.accounts.helpers import signed_in
from tests.factories import UserAccountFactory

ALL = ["clients.view", "clients.manage", "travelers.view", "travelers.manage"]


def _seeded_role(session, name: str) -> Role:
    return session.exec(select(Role).where(Role.name == name)).one()


def test_an_advisor_manages_clients_and_travelers_and_operations_only_reads(
    app, session, auth_client
):
    advisor = auth_client(user=UserAccountFactory(role=_seeded_role(session, "Asesor comercial")))

    # HU-06 CA-01: un primer contacto por WhatsApp, sin documento, y una empresa con NIT.
    person = advisor.post(
        "/api/clients",
        json={
            "client_type": "person",
            "first_name": "Marcela",
            "last_name": "Gómez Ortiz",
            "phone": "300 111 2233",
            "contact_source": "whatsapp",
            "data_consent": True,
        },
    )
    company = advisor.post(
        "/api/clients",
        json={
            "client_type": "company",
            "business_name": "Viajes del Norte SAS",
            "document_type": "NIT",
            "document_number": "800.197.268-4",
            "phone": "601 234 5678",
            "contact_source": "referral",
            "data_consent": True,
        },
    )
    assert (person.status_code, company.status_code) == (201, 201)
    person_id = person.json()["id"]

    # HU-06 CA-02: faltan datos obligatorios.
    incomplete = advisor.post(
        "/api/clients", json={"client_type": "person", "first_name": "Julián", "phone": ""}
    )
    assert incomplete.status_code == 422
    assert {"last_name", "phone", "contact_source", "data_consent"} <= set(
        incomplete.json()["fields"]
    )

    # HU-06 CA-05: lo encuentra por el teléfono con el que escribe y por el nombre.
    by_phone = advisor.get("/api/clients", params={"q": "+57 300 111"}).json()
    by_name = advisor.get("/api/clients", params={"q": "gomez marcela"}).json()
    assert [item["id"] for item in by_phone["results"]] == [person_id]
    assert [item["id"] for item in by_name["results"]] == [person_id]

    # HU-06 CA-03 y CA-04: consulta su ficha y completa el documento y la fecha de nacimiento.
    detail = advisor.get(f"/api/clients/{person_id}").json()
    edited = advisor.put(
        f"/api/clients/{person_id}",
        json={
            "client_type": "person",
            "first_name": detail["first_name"],
            "last_name": detail["last_name"],
            "document_type": "CC",
            "document_number": "1020304050",
            "birth_date": "1988-06-14",
            "phone": detail["phone"],
            "contact_source": detail["contact_source"],
            "expected_version": detail["version"],
        },
    )
    assert edited.status_code == 200
    assert (edited.json()["document_number"], edited.json()["version"]) == ("1020304050", 2)

    # HU-08 CA-01 y CA-05: la clienta también viaja (su ficha de viajero copia sus datos) y
    # registra a su hija menor como viajera de referencia.
    herself = advisor.post(
        "/api/travelers",
        json={
            "first_name": "Marcela",
            "last_name": "Gómez Ortiz",
            "document_type": "CC",
            "document_number": "1020304050",
            "birth_date": "1988-06-14",
            "nationality": "CO",
            "reference_client_id": person_id,
            "is_the_client": True,
            "data_consent": True,
        },
    )
    daughter = advisor.post(
        "/api/travelers",
        json={
            "first_name": "Camila",
            "last_name": "Gómez Ortiz",
            "document_type": "TI",
            "document_number": "1098221334",
            "birth_date": "2012-02-03",
            "nationality": "CO",
            "reference_client_id": person_id,
            "data_consent": True,
        },
    )
    assert (herself.status_code, daughter.status_code) == (201, 201)
    assert daughter.json()["is_minor"] is True

    # HU-08 CA-02: faltan datos obligatorios del viajero.
    missing = advisor.post(
        "/api/travelers", json={"first_name": "Tomás", "nationality": "CO", "data_consent": True}
    )
    assert missing.status_code == 422
    assert {"last_name", "document_type", "document_number", "birth_date"} <= set(
        missing.json()["fields"]
    )

    # HU-08 CA-03 y CA-04: consulta y edita a la viajera.
    traveler = advisor.get(f"/api/travelers/{daughter.json()['id']}").json()
    updated = advisor.put(
        f"/api/travelers/{traveler['id']}",
        json={
            "first_name": traveler["first_name"],
            "last_name": traveler["last_name"],
            "document_type": traveler["document_type"],
            "document_number": traveler["document_number"],
            "birth_date": traveler["birth_date"],
            "nationality": traveler["nationality"],
            "reference_client_id": person_id,
            "notes": "Prefiere ventana.",
            "expected_version": traveler["version"],
        },
    )
    assert (updated.status_code, updated.json()["notes"]) == (200, "Prefiere ventana.")

    # HU-08 CA-05: los datos del viajero no cambian al editar al cliente.
    renamed = advisor.put(
        f"/api/clients/{person_id}",
        json={
            "client_type": "person",
            "first_name": "Marcela Andrea",
            "last_name": "Gómez Ortiz",
            "document_type": "CC",
            "document_number": "1020304050",
            "birth_date": "1988-06-14",
            "phone": "300 111 2233",
            "contact_source": "whatsapp",
            "expected_version": 2,
        },
    )
    assert renamed.status_code == 200
    assert advisor.get(f"/api/travelers/{herself.json()['id']}").json()["first_name"] == "Marcela"

    companions = advisor.get("/api/travelers", params={"client_id": person_id}).json()
    assert companions["count"] == 2

    # El rol Operativo ve clientes y viajeros para gestionar el viaje, pero no los modifica.
    operations = signed_in(
        app, session, UserAccountFactory(role=_seeded_role(session, "Operativo"))
    )
    assert operations.get(f"/api/clients/{person_id}").status_code == 200
    assert operations.get("/api/travelers", params={"client_id": person_id}).status_code == 200
    assert operations.post("/api/clients", json={}).status_code == 403
    assert operations.put(f"/api/travelers/{traveler['id']}", json={}).status_code == 403
