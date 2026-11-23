"""Alta, edición y cambios de estado de una cotización.

Cada operación hace un solo `commit()`. Solo se edita una cotización en borrador. Los estados
van `borrador -> enviada -> aceptada | rechazada`; una enviada o rechazada puede volver a
borrador para corregirla, y una aceptada ya no cambia (de ahí sale la venta).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.errors import InvalidFields, StaleVersion
from app.quotes.errors import (
    UNKNOWN_REQUEST,
    VALIDITY_IN_PAST,
    QuoteExpired,
    QuoteNotEditable,
    QuoteWithoutExchangeRate,
    QuoteWithoutItems,
    QuoteWrongStatus,
)
from app.quotes.models import Quote, QuoteItem, QuoteStatus
from app.quotes.schemas import (
    QuoteConditionsUpdate,
    QuoteCreate,
    QuoteGeneralUpdate,
    QuotePricingUpdate,
    QuoteTransition,
)
from app.quotes.services.quote_queries import get_quote
from app.travel_requests.models import DateMode, TravelRequest
from app.travel_requests.services.request_management import ensure_open
from app.travel_requests.services.request_status import refresh_status

# Valores con que nace una cotización; el asesor los cambia en cada una.
DEFAULT_MARKUP_PERCENT = Decimal("15.00")
DEFAULT_VALIDITY_DAYS = 7


def _check_version(quote: Quote, expected_version: int) -> None:
    if expected_version != quote.version:
        raise StaleVersion()


def ensure_draft(quote: Quote) -> None:
    if quote.status != QuoteStatus.DRAFT:
        raise QuoteNotEditable()


def _draft(session: Session, quote_id: int, expected_version: int) -> Quote:
    quote = get_quote(session, quote_id)
    # No editable antes que versión vieja: quien la vea enviada sabe qué hacer, y al recargar
    # se encontraría con el mismo bloqueo.
    ensure_draft(quote)
    _check_version(quote, expected_version)
    return quote


def _in(session: Session, quote_id: int, expected_version: int, *statuses) -> Quote:
    quote = get_quote(session, quote_id)
    if quote.status not in statuses:
        raise QuoteWrongStatus()
    _check_version(quote, expected_version)
    return quote


def _save(session: Session, quote: Quote) -> Quote:
    session.add(quote)
    session.commit()
    return get_quote(session, quote.id)


def _check_validity(valid_until, current=None) -> None:
    # Al editar solo se revisa si cambió: se pueden corregir otros datos de una cotización
    # cuya vigencia ya pasó.
    if valid_until != current and valid_until < today():
        raise InvalidFields(fields={"valid_until": [VALIDITY_IN_PAST]})


def start_quote(session: Session, actor: UserAccount, travel_request_id: int) -> Quote:
    """Arma la cotización desde la solicitud, sin `commit()`: quien la llama completa lo suyo
    (por ejemplo, copiar los servicios de un paquete) en la misma transacción."""
    # FOR UPDATE: crear la cotización cambia el estado de la solicitud, y un cierre
    # simultáneo tiene que esperar o verse.
    request = session.exec(
        select(TravelRequest).where(TravelRequest.id == travel_request_id).with_for_update()
    ).first()
    if request is None:
        raise InvalidFields(fields={"travel_request_id": [UNKNOWN_REQUEST]})
    ensure_open(request)

    # Con un período flexible las fechas quedan vacías: el asesor pone las que va a cotizar.
    exact = request.date_mode == DateMode.EXACT
    quote = Quote(
        travel_request_id=request.id,
        client_id=request.client_id,
        destination=request.destination,
        origin=request.origin,
        departure_date=request.departure_date if exact else None,
        return_date=request.return_date if exact else None,
        adults=request.adults,
        minors=request.minors,
        valid_until=today() + timedelta(days=DEFAULT_VALIDITY_DAYS),
        default_markup_percent=DEFAULT_MARKUP_PERCENT,
        created_by_id=actor.id,
    )
    session.add(quote)
    session.flush()
    refresh_status(session, request)
    return quote


def create_quote(session: Session, actor: UserAccount, data: QuoteCreate) -> Quote:
    return _save(session, start_quote(session, actor, data.travel_request_id))


def update_general(session: Session, quote_id: int, data: QuoteGeneralUpdate) -> Quote:
    quote = _draft(session, quote_id, data.expected_version)
    _check_validity(data.valid_until, quote.valid_until)
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(quote, name, value)
    return _save(session, quote)


def update_conditions(session: Session, quote_id: int, data: QuoteConditionsUpdate) -> Quote:
    quote = _draft(session, quote_id, data.expected_version)
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(quote, name, value)
    return _save(session, quote)


def update_pricing(session: Session, quote_id: int, data: QuotePricingUpdate) -> Quote:
    quote = _draft(session, quote_id, data.expected_version)
    quote.default_markup_percent = data.default_markup_percent
    quote.exchange_rate = data.exchange_rate
    return _save(session, quote)


def send_quote(session: Session, quote_id: int, data: QuoteTransition) -> Quote:
    quote = _in(session, quote_id, data.expected_version, QuoteStatus.DRAFT)
    items = session.exec(
        select(func.count()).select_from(QuoteItem).where(QuoteItem.quote_id == quote.id)
    ).one()
    if not items:
        raise QuoteWithoutItems()
    if quote.totals.missing_exchange_rate:
        raise QuoteWithoutExchangeRate()
    _check_validity(quote.valid_until)
    quote.status = QuoteStatus.SENT
    quote.sent_at = datetime.now(timezone.utc)
    return _save(session, quote)


def return_to_draft(session: Session, quote_id: int, data: QuoteTransition) -> Quote:
    quote = _in(session, quote_id, data.expected_version, QuoteStatus.SENT, QuoteStatus.REJECTED)
    quote.status = QuoteStatus.DRAFT
    quote.sent_at = None
    quote.decided_at = None
    return _save(session, quote)


def accept_quote(session: Session, quote_id: int, data: QuoteTransition) -> Quote:
    quote = _in(session, quote_id, data.expected_version, QuoteStatus.SENT)
    if quote.is_expired:
        raise QuoteExpired()
    quote.status = QuoteStatus.ACCEPTED
    quote.decided_at = datetime.now(timezone.utc)
    return _save(session, quote)


def reject_quote(session: Session, quote_id: int, data: QuoteTransition) -> Quote:
    quote = _in(session, quote_id, data.expected_version, QuoteStatus.SENT)
    quote.status = QuoteStatus.REJECTED
    quote.decided_at = datetime.now(timezone.utc)
    return _save(session, quote)
