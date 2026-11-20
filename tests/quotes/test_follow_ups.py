from datetime import date, timedelta

import pytest

from app.common.dates import today
from app.quotes.follow_up_models import AlertColor, QuoteFollowUp, alert_color
from tests.factories import QuoteFactory

MANAGE = ["quotes.view", "quotes.manage"]


def in_days(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


@pytest.mark.parametrize(
    "offset, color",
    [(-1, AlertColor.RED), (0, AlertColor.YELLOW), (1, AlertColor.YELLOW), (2, AlertColor.GREEN)],
)
def test_the_traffic_light(offset, color):
    day = date(2026, 11, 20)
    assert alert_color(day + timedelta(days=offset), day) == color


@pytest.fixture
def api(auth_client):
    return auth_client(permissions=MANAGE)


def schedule(api, quote, days: int, purpose="Confirmar si recibió la propuesta") -> dict:
    response = api.post(
        f"/api/quotes/{quote.id}/follow-ups",
        json={"due_date": in_days(days), "channel": "whatsapp", "purpose": purpose},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_scheduling_and_listing_by_color(api):
    quote = QuoteFactory(sent=True)
    late = schedule(api, quote, -2)
    soon = schedule(api, quote, 1)
    later = schedule(api, quote, 5)

    def ids(alert: str) -> list[int]:
        rows = api.get("/api/follow-ups", params={"alert": alert}).json()["results"]
        return [row["id"] for row in rows]

    assert (ids("red"), ids("yellow"), ids("green")) == ([late["id"]], [soon["id"]], [later["id"]])
    assert late["alert"] == "red"
    assert late["quote"]["code"] == quote.code
    assert api.get("/api/follow-ups/alerts").json() == {"red": 1, "yellow": 1, "green": 1}


def test_completing_registers_the_outcome_and_can_schedule_the_next(api, session):
    quote = QuoteFactory(sent=True)
    follow_up = schedule(api, quote, 0)

    response = api.post(
        f"/api/follow-ups/{follow_up['id']}/complete",
        json={"outcome": "Lo está pensando con la familia.", "next_due_date": in_days(3)},
    )

    assert response.status_code == 200, response.json()
    done = response.json()
    assert (done["status"], done["alert"], done["done_by"] is not None) == ("done", None, True)
    pending = api.get(
        "/api/follow-ups", params={"quote_id": quote.id, "status": "pending"}
    ).json()["results"]
    assert [(row["due_date"], row["purpose"]) for row in pending] == [
        (in_days(3), "Confirmar si recibió la propuesta")
    ]
    again = api.post(f"/api/follow-ups/{follow_up['id']}/complete", json={})
    assert again.json()["code"] == "follow_up_done"


def test_a_decided_quote_needs_no_follow_up(api):
    quote = QuoteFactory(accepted=True)

    response = api.post(
        f"/api/quotes/{quote.id}/follow-ups",
        json={"due_date": in_days(1), "channel": "call", "purpose": "Llamar"},
    )

    assert response.json()["code"] == "quote_closed"


def test_a_pending_follow_up_can_be_removed(api, session):
    follow_up = schedule(api, QuoteFactory(), 2)

    assert api.delete(f"/api/follow-ups/{follow_up['id']}").status_code == 204
    assert session.get(QuoteFollowUp, follow_up["id"]) is None


def test_viewing_is_not_enough_to_schedule(auth_client):
    viewer = auth_client(permissions=["quotes.view"])

    response = viewer.post(
        f"/api/quotes/{QuoteFactory().id}/follow-ups",
        json={"due_date": in_days(1), "channel": "call", "purpose": "Llamar"},
    )

    assert response.status_code == 403
