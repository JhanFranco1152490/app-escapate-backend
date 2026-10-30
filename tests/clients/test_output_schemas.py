from datetime import date

from app.clients import models
from app.clients.schemas import ClientDetail, ClientListItem, TravelerDetail, TravelerListItem
from tests.factories import ClientFactory, TravelerFactory, UserAccountFactory


def test_the_client_detail_says_who_registered_it_and_who_recorded_the_consent(session):
    advisor = UserAccountFactory(first_name="Laura", last_name="Rojas")
    client = ClientFactory(created_by=advisor, notes="Viaja con su familia.")
    session.refresh(client)

    detail = ClientDetail.model_validate(client)

    assert detail.created_by.model_dump() == {"id": advisor.id, "full_name": "Laura Rojas"}
    assert detail.data_consent_by == detail.created_by
    assert detail.notes == "Viaja con su familia."
    assert detail.version == 1


def test_the_client_list_item_uses_the_display_name(session):
    company = ClientFactory(company=True, business_name="Viajes del Norte SAS")

    item = ClientListItem.model_validate(company)

    assert item.display_name == "Viajes del Norte SAS"
    assert "notes" not in item.model_dump()


def test_the_traveler_shows_its_reference_client_and_its_age(session, monkeypatch):
    monkeypatch.setattr(models, "today", lambda: date(2026, 10, 25))
    client = ClientFactory(first_name="Marcela", last_name="Gómez Ortiz")
    traveler = TravelerFactory(reference_client=client, birth_date=date(2012, 2, 3))
    session.refresh(traveler)

    item = TravelerListItem.model_validate(traveler)
    detail = TravelerDetail.model_validate(traveler)

    assert item.reference_client.model_dump() == {
        "id": client.id,
        "display_name": "Marcela Gómez Ortiz",
    }
    assert (item.age, item.is_minor) == (14, True)
    assert "notes" not in item.model_dump()
    assert detail.created_by.id == traveler.created_by_id


def test_a_traveler_without_a_reference_client(session):
    item = TravelerListItem.model_validate(TravelerFactory())

    assert item.reference_client is None
