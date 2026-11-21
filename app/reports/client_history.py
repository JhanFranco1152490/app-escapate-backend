"""El historial de un cliente: sus solicitudes, cotizaciones, ventas y pagos en una sola línea
de tiempo, con el resumen de lo que ha comprado y lo que debe."""

from datetime import datetime, time
from enum import StrEnum

from pydantic import BaseModel
from sqlmodel import Session, select

from app.clients.models import Client
from app.common.dates import BOGOTA
from app.common.errors import NotFound
from app.quotes.models import Quote
from app.sales.models import ClientPayment, Sale
from app.travel_requests.models import TravelRequest


class EventKind(StrEnum):
    REQUEST = "request"
    QUOTE = "quote"
    SALE = "sale"
    PAYMENT = "payment"


class HistoryEvent(BaseModel):
    kind: EventKind
    at: datetime
    record_id: int
    code: str
    title: str
    status: str | None
    amount: int | None


class ClientHistory(BaseModel):
    requests: int
    quotes: int
    sales: int
    total_bought: int
    total_paid: int
    balance: int
    last_activity: datetime | None
    events: list[HistoryEvent]


def _at_noon(day) -> datetime:
    # Un pago tiene fecha sin hora: se ubica a mediodía de Bogotá para ordenarlo con el resto.
    return datetime.combine(day, time(12), BOGOTA)


def client_history(session: Session, client_id: int) -> ClientHistory:
    if session.get(Client, client_id) is None:
        raise NotFound()
    requests = session.exec(
        select(TravelRequest).where(TravelRequest.client_id == client_id)
    ).all()
    quotes = session.exec(select(Quote).where(Quote.client_id == client_id)).all()
    sales = session.exec(select(Sale).where(Sale.client_id == client_id)).all()
    payments = session.exec(
        select(ClientPayment, Sale)
        .join(Sale, Sale.id == ClientPayment.sale_id)
        .where(Sale.client_id == client_id)
    ).all()

    events = [
        HistoryEvent(
            kind=EventKind.REQUEST,
            at=request.created_at,
            record_id=request.id,
            code=request.code,
            title=f"Solicitud de viaje a {request.destination}",
            status=request.status,
            amount=None,
        )
        for request in requests
    ]
    events += [
        HistoryEvent(
            kind=EventKind.QUOTE,
            at=quote.created_at,
            record_id=quote.id,
            code=quote.code,
            title=f"Cotización para {quote.destination}",
            status="expired" if quote.is_expired else quote.status,
            amount=quote.totals.sale,
        )
        for quote in quotes
    ]
    events += [
        HistoryEvent(
            kind=EventKind.SALE,
            at=sale.created_at,
            record_id=sale.id,
            code=sale.code,
            title=f"Venta del viaje a {sale.destination}",
            status=sale.payment_status,
            amount=sale.total_price,
        )
        for sale in sales
    ]
    events += [
        HistoryEvent(
            kind=EventKind.PAYMENT,
            at=_at_noon(payment.paid_on),
            record_id=sale.id,
            code=sale.code,
            title=f"Pago de la venta {sale.code}",
            status=payment.method,
            amount=payment.amount,
        )
        for payment, sale in payments
    ]
    events.sort(key=lambda event: event.at, reverse=True)

    total_bought = sum(sale.total_price for sale in sales)
    total_paid = sum(payment.amount for payment, _ in payments)
    return ClientHistory(
        requests=len(requests),
        quotes=len(quotes),
        sales=len(sales),
        total_bought=total_bought,
        total_paid=total_paid,
        balance=total_bought - total_paid,
        last_activity=events[0].at if events else None,
        events=events,
    )
