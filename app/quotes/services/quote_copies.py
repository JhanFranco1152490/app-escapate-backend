"""Duplicar una cotización o sacar de ella una versión nueva.

Las dos crean un borrador con los mismos datos y servicios, en la misma solicitud. La versión
nueva apunta a la cotización de la que salió y sube el número; el duplicado empieza en la
versión 1. La original no cambia.
"""

from datetime import timedelta

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.quotes.models import Quote, QuoteItem
from app.quotes.schemas import QuoteCopy
from app.quotes.services.quote_management import DEFAULT_VALIDITY_DAYS
from app.quotes.services.quote_queries import get_quote
from app.travel_requests.models import TravelRequest
from app.travel_requests.services.request_management import ensure_open

_COPIED = (
    "travel_request_id",
    "client_id",
    "destination",
    "origin",
    "departure_date",
    "return_date",
    "adults",
    "minors",
    "notes",
    "default_markup_percent",
    "exchange_rate",
    "deposit_percent",
    "balance_due_date",
    "payment_terms",
    "policies",
)

_ITEM_FIELDS = (
    "service_type",
    "tourist_service_id",
    "supplier_id",
    "name",
    "details",
    "start_date",
    "end_date",
    "quantity",
    "charge_unit",
    "is_optional",
    "quality_level",
    "currency",
    "unit_cost",
    "markup_percent",
    "sale_price_override",
    "supplier_commission_percent",
)


def copy_items(session: Session, source: list[QuoteItem], quote_id: int) -> None:
    """Copia los servicios a otra cotización, con sus alternativas apuntando a las copias."""
    copies: dict[int, QuoteItem] = {}
    for item in source:
        copy = QuoteItem(quote_id=quote_id, **{name: getattr(item, name) for name in _ITEM_FIELDS})
        session.add(copy)
        copies[item.id] = copy
    session.flush()
    for item in source:
        if item.alternative_of_id in copies:
            copies[item.id].alternative_of_id = copies[item.alternative_of_id].id


def copy_quote(session: Session, actor: UserAccount, quote_id: int, data: QuoteCopy) -> Quote:
    original = get_quote(session, quote_id)
    request = session.exec(
        select(TravelRequest).where(TravelRequest.id == original.travel_request_id)
    ).one()
    ensure_open(request)

    copy = Quote(
        **{name: getattr(original, name) for name in _COPIED},
        valid_until=max(original.valid_until, today() + timedelta(days=DEFAULT_VALIDITY_DAYS)),
        previous_quote_id=original.id if data.as_new_version else None,
        revision=original.revision + 1 if data.as_new_version else 1,
        created_by_id=actor.id,
    )
    session.add(copy)
    session.flush()
    copy_items(session, list(original.items), copy.id)
    session.commit()
    return get_quote(session, copy.id)
