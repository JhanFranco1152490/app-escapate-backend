from datetime import timedelta

import pytest

from app.common.dates import today
from app.core.security.csrf import CSRF_HEADER
from tests.factories import (
    ClientFactory,
    QuoteFactory,
    QuoteItemFactory,
    TouristServiceFactory,
    TravelRequestFactory,
    UserAccountFactory,
)

READ_ENDPOINTS = [("get", "/api/quotes"), ("get", "/api/quotes/1")]
WRITE_ENDPOINTS = [
    ("post", "/api/quotes"),
    ("put", "/api/quotes/1"),
    ("put", "/api/quotes/1/conditions"),
    ("put", "/api/quotes/1/pricing"),
    ("post", "/api/quotes/1/send"),
    ("post", "/api/quotes/1/return-to-draft"),
    ("post", "/api/quotes/1/accept"),
    ("post", "/api/quotes/1/reject"),
    ("post", "/api/quotes/1/items"),
    ("put", "/api/quotes/1/items/1"),
    ("delete", "/api/quotes/1/items/1"),
]


@pytest.fixture
def advisor(session, advisor_role):
    return UserAccountFactory(role=advisor_role, first_name="Laura", last_name="Rojas")


@pytest.fixture
def manager(auth_client, advisor):
    return auth_client(user=advisor)


def in_days(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


def create(api, travel_request) -> dict:
    response = api.post("/api/quotes", json={"travel_request_id": travel_request.id})
    assert response.status_code == 201, response.json()
    return response.json()


def general(detail: dict, **changes) -> dict:
    fields = [
        "destination",
        "origin",
        "departure_date",
        "return_date",
        "adults",
        "minors",
        "valid_until",
        "notes",
    ]
    return {name: detail[name] for name in fields} | {
        "expected_version": detail["version"],
        **changes,
    }


def new_item(**changes) -> dict:
    return {
        "service_type": "lodging",
        "name": "Hotel Las Américas",
        "details": "Habitación doble con desayuno.",
        "start_date": in_days(30),
        "end_date": in_days(34),
        "quantity": 4,
        "charge_unit": "per_night",
        "currency": "COP",
        "unit_cost": "450000",
        **changes,
    }


def transition(api, quote: dict, action: str):
    return api.post(
        f"/api/quotes/{quote['id']}/{action}", json={"expected_version": quote["version"]}
    )


# --- Acceso --------------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_a_session_every_endpoint_answers_401(csrf_client, method, path):
    assert csrf_client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_without_the_permission_every_endpoint_answers_403(auth_client, method, path):
    client = auth_client(permissions=["travel_requests.view"])

    response = client.request(method, path, json={})

    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_viewing_is_not_enough_to_change_quotes(auth_client, method, path):
    client = auth_client(permissions=["quotes.view"])

    assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize("method, path", WRITE_ENDPOINTS)
def test_changes_need_the_csrf_token(manager, method, path):
    del manager.headers[CSRF_HEADER]

    assert manager.request(method, path, json={}).status_code == 403


# --- Crear (HU-22) -------------------------------------------------------------------------


def test_creating_copies_the_request_and_marks_it_quoted(manager, advisor, session):
    client = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    request = TravelRequestFactory(
        client=client,
        destination="Cartagena",
        origin="Cúcuta",
        return_date=today() + timedelta(days=35),
        adults=2,
        minors=1,
    )

    created = create(manager, request)

    assert created["code"] == f"COT-{created['id']:04d}"
    assert created["status"] == "draft"
    assert created["client"] == {"id": client.id, "display_name": "Marcela Gómez Ortiz"}
    assert created["travel_request"]["id"] == request.id
    assert (created["destination"], created["origin"]) == ("Cartagena", "Cúcuta")
    assert created["departure_date"] == request.departure_date.isoformat()
    assert created["return_date"] == request.return_date.isoformat()
    assert (created["adults"], created["minors"]) == (2, 1)
    assert created["valid_until"] == in_days(7)
    assert created["default_markup_percent"] == "15.00"
    assert created["created_by"]["id"] == advisor.id
    assert created["items"] == []
    session.refresh(request)
    assert request.status == "quoted"


def test_a_flexible_request_leaves_the_dates_for_the_advisor(manager):
    created = create(manager, TravelRequestFactory(flexible=True))

    assert (created["departure_date"], created["return_date"]) == (None, None)


def test_a_closed_request_cannot_be_quoted(manager):
    response = manager.post(
        "/api/quotes", json={"travel_request_id": TravelRequestFactory(closed=True).id}
    )

    assert (response.status_code, response.json()["code"]) == (409, "travel_request_closed")


def test_an_unknown_request_is_a_field_error(manager):
    response = manager.post("/api/quotes", json={"travel_request_id": 999_999})

    assert response.status_code == 422
    assert response.json()["fields"] == {"travel_request_id": ["La solicitud no existe."]}


def test_reopening_a_quoted_request_keeps_it_quoted(manager, session):
    request = TravelRequestFactory()
    create(manager, request)
    session.refresh(request)
    closed = manager.post(
        f"/api/travel-requests/{request.id}/close",
        json={"reason": "no_response", "expected_version": request.version},
    ).json()

    reopened = manager.post(
        f"/api/travel-requests/{request.id}/reopen",
        json={"expected_version": closed["version"]},
    )

    assert reopened.json()["status"] == "quoted"


# --- Consultar -----------------------------------------------------------------------------


def test_the_list_searches_by_code_client_and_destination(manager):
    marcela = QuoteFactory(
        travel_request__client=ClientFactory(first_name="Marcela", last_name="Gómez"),
        destination="Cartagena",
    )
    other = QuoteFactory(destination="Santa Marta")

    def found(text: str) -> list[int]:
        return [
            row["id"] for row in manager.get("/api/quotes", params={"q": text}).json()["results"]
        ]

    assert found("marcela") == [marcela.id]
    assert found("santa marta") == [other.id]
    assert found(f"COT-{other.id:04d}") == [other.id]


def test_sent_and_expired_are_separate_filters(manager):
    current = QuoteFactory(sent=True)
    expired = QuoteFactory(sent=True, valid_until=today() - timedelta(days=1))
    QuoteFactory()

    def ids(status: str) -> list[int]:
        page = manager.get("/api/quotes", params={"status": status}).json()
        return [row["id"] for row in page["results"]]

    assert ids("sent") == [current.id]
    assert ids("expired") == [expired.id]
    detail = manager.get(f"/api/quotes/{expired.id}").json()
    assert detail["is_expired"] is True


def test_an_unknown_quote_answers_404(manager):
    assert manager.get("/api/quotes/999999").status_code == 404


# --- Información general y condiciones (HU-23, HU-27) --------------------------------------


def test_editing_the_general_information(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}",
        json=general(
            quote,
            destination="Cartagena y Barú",
            departure_date=in_days(40),
            return_date=in_days(45),
            minors=2,
            notes="Cliente prefiere hoteles con piscina.",
        ),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["destination"], body["minors"]) == ("Cartagena y Barú", 2)
    assert body["version"] == quote["version"] + 1


def test_the_return_cannot_be_before_the_departure(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}",
        json=general(quote, departure_date=in_days(40), return_date=in_days(39)),
    )

    assert list(response.json()["fields"]) == ["return_date"]


def test_a_new_validity_cannot_be_in_the_past(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}", json=general(quote, valid_until=in_days(-1))
    )

    assert response.json()["fields"] == {"valid_until": ["La vigencia ya pasó."]}


def test_an_old_version_is_rejected(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}", json=general(quote, expected_version=quote["version"] + 5)
    )

    assert (response.status_code, response.json()["code"]) == (409, "stale_version")


def test_setting_the_commercial_conditions(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}/conditions",
        json={
            "deposit_percent": "30",
            "balance_due_date": in_days(20),
            "payment_terms": "Abono del 30 % para reservar.\nSaldo 10 días antes del viaje.",
            "policies": "Tarifas sujetas a disponibilidad.",
            "expected_version": quote["version"],
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["deposit_percent"] == "30.00"
    assert body["payment_terms"].startswith("Abono del 30 %")


def test_the_deposit_is_a_percentage(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.put(
        f"/api/quotes/{quote['id']}/conditions",
        json={"deposit_percent": "120", "expected_version": quote["version"]},
    )

    assert list(response.json()["fields"]) == ["deposit_percent"]


# --- Servicios (HU-24) ---------------------------------------------------------------------


def test_adding_a_service_written_by_hand(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.post(f"/api/quotes/{quote['id']}/items", json=new_item())

    assert response.status_code == 201, response.json()
    item = response.json()
    assert (item["name"], item["quantity"], item["unit_cost"]) == (
        "Hotel Las Américas",
        4,
        "450000",
    )
    # Sin % propio toma el de la cotización.
    assert item["markup_percent"] == "15.00"
    assert item["supplier"] is None
    detail = manager.get(f"/api/quotes/{quote['id']}").json()
    assert [row["id"] for row in detail["items"]] == [item["id"]]


def test_a_catalog_service_brings_its_supplier(manager):
    service = TouristServiceFactory(service_type="lodging")
    quote = create(manager, TravelRequestFactory())

    item = manager.post(
        f"/api/quotes/{quote['id']}/items", json=new_item(tourist_service_id=service.id)
    ).json()

    assert item["tourist_service"] == {"id": service.id, "name": service.name}
    assert item["supplier"] == {
        "id": service.supplier.id,
        "trade_name": service.supplier.trade_name,
    }


def test_a_catalog_service_must_be_active_and_of_the_same_type(manager):
    service = TouristServiceFactory(inactive=True, service_type="lodging")
    quote = create(manager, TravelRequestFactory())

    response = manager.post(
        f"/api/quotes/{quote['id']}/items",
        json=new_item(tourist_service_id=service.id, service_type="air", charge_unit=None),
    )

    assert response.json()["fields"] == {
        "tourist_service_id": ["El servicio está inactivo."],
        "service_type": ["No coincide con el tipo del servicio elegido."],
    }


def test_the_charge_unit_belongs_to_the_service_type(manager):
    quote = create(manager, TravelRequestFactory())

    response = manager.post(
        f"/api/quotes/{quote['id']}/items",
        json=new_item(service_type="air", charge_unit="per_night"),
    )

    assert list(response.json()["fields"]) == ["charge_unit"]


def test_pesos_go_without_cents_but_dollars_keep_them(manager):
    quote = create(manager, TravelRequestFactory())
    url = f"/api/quotes/{quote['id']}/items"

    pesos = manager.post(url, json=new_item(unit_cost="450000.50"))
    dollars = manager.post(url, json=new_item(currency="USD", unit_cost="120.50"))

    assert list(pesos.json()["fields"]) == ["unit_cost"]
    assert dollars.json()["unit_cost"] == "120.50"


def test_editing_and_removing_a_service(manager):
    quote = create(manager, TravelRequestFactory())
    url = f"/api/quotes/{quote['id']}/items"
    item = manager.post(url, json=new_item()).json()

    edited = manager.put(
        f"{url}/{item['id']}",
        json=new_item(quantity=5, markup_percent="20", expected_version=item["version"]),
    )
    removed = manager.delete(f"{url}/{item['id']}")

    assert (edited.json()["quantity"], edited.json()["markup_percent"]) == (5, "20.00")
    assert removed.status_code == 204
    assert manager.get(f"/api/quotes/{quote['id']}").json()["items"] == []


def test_a_service_of_another_quote_is_not_found(manager):
    quote = create(manager, TravelRequestFactory())
    foreign = QuoteItemFactory()

    response = manager.delete(f"/api/quotes/{quote['id']}/items/{foreign.id}")

    assert response.status_code == 404


# --- Estados -------------------------------------------------------------------------------


def test_a_quote_without_services_cannot_be_sent(manager):
    quote = create(manager, TravelRequestFactory())

    response = transition(manager, quote, "send")

    assert (response.status_code, response.json()["code"]) == (409, "quote_without_items")


def test_a_sent_quote_is_no_longer_editable(manager):
    quote = create(manager, TravelRequestFactory())
    manager.post(f"/api/quotes/{quote['id']}/items", json=new_item())
    sent = transition(manager, quote, "send").json()

    edit = manager.put(f"/api/quotes/{quote['id']}", json=general(sent))
    add = manager.post(f"/api/quotes/{quote['id']}/items", json=new_item())

    assert sent["status"] == "sent" and sent["sent_at"] is not None
    assert edit.json()["code"] == add.json()["code"] == "quote_not_editable"


def test_the_full_cycle_send_reject_redraft_accept(manager):
    quote = create(manager, TravelRequestFactory())
    manager.post(f"/api/quotes/{quote['id']}/items", json=new_item())

    sent = transition(manager, quote, "send").json()
    rejected = transition(manager, sent, "reject").json()
    draft = transition(manager, rejected, "return-to-draft").json()
    accepted = transition(manager, transition(manager, draft, "send").json(), "accept").json()

    assert rejected["decided_at"] is not None
    assert (draft["status"], draft["sent_at"], draft["decided_at"]) == ("draft", None, None)
    assert accepted["status"] == "accepted"


def test_an_expired_quote_cannot_be_accepted(manager):
    quote = QuoteFactory(sent=True, valid_until=today() - timedelta(days=1))
    detail = manager.get(f"/api/quotes/{quote.id}").json()

    response = transition(manager, detail, "accept")

    assert (response.status_code, response.json()["code"]) == (409, "quote_expired")


def test_an_accepted_quote_does_not_go_back_to_draft(manager):
    quote = QuoteFactory(sent=True)
    accepted = transition(manager, manager.get(f"/api/quotes/{quote.id}").json(), "accept").json()

    response = transition(manager, accepted, "return-to-draft")

    assert (response.status_code, response.json()["code"]) == (409, "quote_wrong_status")
