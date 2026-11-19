"""Recorridos de HU-10 (registrar solicitudes), HU-11 (gestionarlas), HU-13 (pendientes de
cotización) y HU-09 (viajeros de la solicitud) desde la API, con los permisos reales de los
roles sembrados."""

from datetime import timedelta

from app.common.dates import today
from tests.accounts.helpers import signed_in
from tests.factories import ClientFactory, TravelerFactory, UserAccountFactory


def _in_days(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


def _pending_ids(api) -> list[int]:
    page = api.get("/api/travel-requests", params={"status": "pending", "sort": "oldest"})
    assert page.status_code == 200
    return [item["id"] for item in page.json()["results"]]


def test_an_advisor_takes_a_request_from_registration_to_closing_and_operations_only_reads(
    app, session, auth_client, advisor_role, operations_role
):
    laura = UserAccountFactory(role=advisor_role, first_name="Laura", last_name="Rojas")
    andres = UserAccountFactory(role=advisor_role, first_name="Andrés", last_name="Quintero")
    advisor = auth_client(user=laura)
    client = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    base = {
        "client_id": client.id,
        "destination": "San Andrés",
        "adults": 2,
        "minors": 1,
        "assigned_to_id": laura.id,
    }

    # HU-10 CA-02: faltan datos obligatorios.
    incomplete = advisor.post("/api/travel-requests", json={**base, "date_mode": "exact"})
    assert incomplete.status_code == 422
    assert set(incomplete.json()["fields"]) == {"departure_date"}

    # HU-10 CA-01, CA-03 y CA-05: dos solicitudes del mismo cliente, cada una con lo suyo.
    exact = advisor.post(
        "/api/travel-requests",
        json={
            **base,
            "date_mode": "exact",
            "departure_date": _in_days(35),
            "return_date": _in_days(41),
            "trip_types": ["family"],
            "notes": "Prefieren habitación conectada.",
        },
    )
    flexible = advisor.post(
        "/api/travel-requests",
        json={
            **base,
            "destination": "Cartagena",
            "date_mode": "flexible",
            "window_start": _in_days(60),
            "window_end": _in_days(90),
            "approx_nights": 5,
        },
    )
    assert (exact.status_code, flexible.status_code) == (201, 201)
    first, second = exact.json(), flexible.json()
    assert first["id"] != second["id"]

    # HU-13 CA-01: las dos esperan cotización, la más antigua primero.
    assert _pending_ids(advisor) == [first["id"], second["id"]]

    # HU-10 CA-04 y HU-11 CA-01: la ficha muestra lo que se registró.
    detail = advisor.get(f"/api/travel-requests/{first['id']}").json()
    assert (detail["trip_types"], detail["notes"]) == (
        ["family"],
        "Prefieren habitación conectada.",
    )

    # HU-11 CA-02: se edita y se reasigna a otro asesor; la otra solicitud no cambia (CA-04).
    edited = advisor.put(
        f"/api/travel-requests/{first['id']}",
        json={
            **base,
            "date_mode": "exact",
            "departure_date": _in_days(35),
            "minors": 2,
            "assigned_to_id": andres.id,
            "expected_version": detail["version"],
        },
    )
    assert edited.status_code == 200
    assert (edited.json()["minors"], edited.json()["assigned_to"]["id"]) == (2, andres.id)
    assert advisor.get(f"/api/travel-requests/{second['id']}").json()["version"] == 1
    mine = advisor.get("/api/travel-requests", params={"assigned_to": andres.id}).json()
    assert [item["id"] for item in mine["results"]] == [first["id"]]

    # HU-11 CA-03: quitar un dato obligatorio no guarda nada.
    broken = advisor.put(
        f"/api/travel-requests/{first['id']}",
        json={**base, "date_mode": "exact", "expected_version": edited.json()["version"]},
    )
    assert broken.status_code == 422

    # HU-13 CA-02: cerrada deja de estar pendiente; reabierta vuelve.
    closed = advisor.post(
        f"/api/travel-requests/{first['id']}/close",
        json={"reason": "client_declined", "expected_version": edited.json()["version"]},
    )
    assert closed.status_code == 200
    assert _pending_ids(advisor) == [second["id"]]
    reopened = advisor.post(
        f"/api/travel-requests/{first['id']}/reopen",
        json={"expected_version": closed.json()["version"]},
    )
    assert reopened.status_code == 200
    assert _pending_ids(advisor) == [first["id"], second["id"]]

    # El Operativo consulta pero no modifica.
    operations = signed_in(app, session, UserAccountFactory(role=operations_role))
    assert operations.get(f"/api/travel-requests/{first['id']}").status_code == 200
    assert operations.get("/api/travel-requests/summary").json()["pending"] == 2
    denied = operations.post(
        f"/api/travel-requests/{first['id']}/close",
        json={"reason": "duplicate", "expected_version": reopened.json()["version"]},
    )
    assert denied.status_code == 403


def test_an_advisor_chooses_who_travels_and_operations_only_reads(
    app, session, auth_client, advisor_role, operations_role
):
    """Recorrido de HU-09 (asociar viajeros al proceso de viaje)."""
    laura = UserAccountFactory(role=advisor_role, first_name="Laura", last_name="Rojas")
    advisor = auth_client(user=laura)
    client = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    created = advisor.post(
        "/api/travel-requests",
        json={
            "client_id": client.id,
            "destination": "San Andrés",
            "date_mode": "exact",
            "departure_date": _in_days(35),
            "adults": 2,
            "minors": 1,
            "assigned_to_id": laura.id,
        },
    ).json()
    travelers_url = f"/api/travel-requests/{created['id']}/travelers"
    titular = TravelerFactory(reference_client=client, is_the_client=True)
    daughter = TravelerFactory(
        reference_client=client, document_type="TI", birth_date=today() - timedelta(days=14 * 365)
    )
    friend = TravelerFactory()

    # Los viajeros de referencia del cliente son los que la pantalla sugiere primero.
    suggested = advisor.get("/api/travelers", params={"client_id": client.id}).json()
    assert {item["id"] for item in suggested["results"]} == {titular.id, daughter.id}

    # CA-01 y CA-04: se asocian varios a la vez, cada uno con sus propios datos.
    added = advisor.post(
        travelers_url, json={"traveler_ids": [titular.id, daughter.id, friend.id]}
    )
    assert added.status_code == 200
    by_id = {item["id"]: item for item in added.json()}
    assert by_id[titular.id]["is_the_client"] is True
    assert by_id[daughter.id]["is_minor"] is True
    assert by_id[friend.id]["is_the_client"] is False

    # CA-02: aparecen entre los participantes.
    assert len(advisor.get(travelers_url).json()) == 3

    # CA-03: quitar al que se asoció por error no borra sus datos.
    assert advisor.delete(f"{travelers_url}/{friend.id}").status_code == 204
    assert {item["id"] for item in advisor.get(travelers_url).json()} == {
        titular.id,
        daughter.id,
    }
    assert advisor.get(f"/api/travelers/{friend.id}").status_code == 200

    # Cerrada no cambia sus viajeros; reabierta los conserva.
    request = advisor.get(f"/api/travel-requests/{created['id']}").json()
    assert request["version"] == created["version"]
    closed = advisor.post(
        f"/api/travel-requests/{created['id']}/close",
        json={"reason": "client_declined", "expected_version": request["version"]},
    ).json()
    blocked = advisor.post(travelers_url, json={"traveler_ids": [friend.id]})
    assert (blocked.status_code, blocked.json()["code"]) == (409, "travel_request_closed")
    advisor.post(
        f"/api/travel-requests/{created['id']}/reopen",
        json={"expected_version": closed["version"]},
    )
    assert len(advisor.get(travelers_url).json()) == 2

    # El Operativo ve quién viaja pero no lo cambia.
    operations = signed_in(app, session, UserAccountFactory(role=operations_role))
    assert len(operations.get(travelers_url).json()) == 2
    assert operations.delete(f"{travelers_url}/{titular.id}").status_code == 403
