"""Ventas y pagos de clientes.

Registrar una venta y registrar un pago corren cada uno en una sola transacción: la cotización
y la venta se leen con `FOR UPDATE`, así dos ventas de la misma cotización o dos pagos
simultáneos que juntos pasan el saldo no quedan los dos guardados.
"""

from fastapi import Request
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.audit.models import DeletionKind
from app.audit.services import record_deletion
from app.clients.models import Client
from app.clients.services.client_queries import display_name
from app.common.errors import ApiError, InvalidFields, NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import has_every_word, name_or_document
from app.quotes.models import Quote, QuoteStatus
from app.quotes.services.quote_queries import get_quote
from app.sales.models import SALE_CODE, ClientPayment, PaymentStatus, Sale
from app.sales.schemas import PaymentCreate, SaleCreate, SaleFilters


class QuoteNotAccepted(ApiError):
    status_code, code = 409, "quote_not_accepted"
    detail = "Solo se vende una cotización aceptada por el cliente."


class QuoteAlreadySold(ApiError):
    status_code, code = 409, "quote_already_sold"
    detail = "Esta cotización ya tiene una venta registrada."


AMOUNT_OVER_BALANCE = "El pago supera el saldo pendiente."

_paid = (
    select(func.coalesce(func.sum(ClientPayment.amount), 0))
    .where(ClientPayment.sale_id == Sale.id)
    .correlate(Sale)
    .scalar_subquery()
)


def _options():
    return [
        joinedload(Sale.client),
        joinedload(Sale.quote),
        joinedload(Sale.created_by),
        selectinload(Sale.payments).joinedload(ClientPayment.created_by),
    ]


def get_sale(session: Session, sale_id: int) -> Sale:
    sale = session.get(Sale, sale_id, options=_options())
    if sale is None:
        raise NotFound()
    return sale


def list_sales(
    session: Session, filters: SaleFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Sale)
    if filters.q:
        clients = select(Client.id).where(
            or_(*name_or_document(display_name, col(Client.document_number), filters.q))
        )
        conditions = [
            col(Sale.client_id).in_(clients),
            has_every_word(col(Sale.destination), filters.q),
        ]
        sale_id = SALE_CODE.parse(filters.q)
        if sale_id is not None:
            conditions.append(col(Sale.id) == sale_id)
        statement = statement.where(or_(*conditions))
    if filters.payment_status == PaymentStatus.PENDING:
        statement = statement.where(_paid == 0)
    elif filters.payment_status == PaymentStatus.PARTIAL:
        statement = statement.where(_paid > 0, _paid < col(Sale.total_price))
    elif filters.payment_status == PaymentStatus.PAID:
        statement = statement.where(_paid >= col(Sale.total_price))
    if filters.quote_id is not None:
        statement = statement.where(col(Sale.quote_id) == filters.quote_id)
    if filters.client_id is not None:
        statement = statement.where(col(Sale.client_id) == filters.client_id)
    statement = statement.options(*_options()).order_by(
        col(Sale.created_at).desc(), col(Sale.id).desc()
    )
    return paginate(session, statement, params, request)


def create_sale(session: Session, actor: UserAccount, data: SaleCreate) -> Sale:
    locked = session.exec(select(Quote).where(Quote.id == data.quote_id).with_for_update()).first()
    if locked is None:
        raise InvalidFields(fields={"quote_id": ["La cotización no existe."]})
    if locked.status != QuoteStatus.ACCEPTED:
        raise QuoteNotAccepted()
    if session.exec(select(Sale.id).where(Sale.quote_id == locked.id)).first():
        raise QuoteAlreadySold()

    quote = get_quote(session, locked.id)
    totals = quote.totals
    sale = Sale(
        quote_id=quote.id,
        client_id=quote.client_id,
        destination=quote.destination,
        departure_date=quote.departure_date,
        return_date=quote.return_date,
        adults=quote.adults,
        minors=quote.minors,
        total_price=data.total_price or totals.sale,
        total_cost=totals.cost,
        notes=data.notes,
        created_by_id=actor.id,
    )
    if sale.total_price <= 0:
        raise InvalidFields(fields={"total_price": ["Indica el precio de la venta."]})
    session.add(sale)
    session.commit()
    return get_sale(session, sale.id)


def add_payment(session: Session, actor: UserAccount, sale_id: int, data: PaymentCreate) -> Sale:
    locked = session.exec(select(Sale).where(Sale.id == sale_id).with_for_update()).first()
    if locked is None:
        raise NotFound()
    paid = session.exec(
        select(func.coalesce(func.sum(ClientPayment.amount), 0)).where(
            ClientPayment.sale_id == sale_id
        )
    ).one()
    if data.amount > locked.total_price - paid:
        raise InvalidFields(fields={"amount": [AMOUNT_OVER_BALANCE]})
    session.add(ClientPayment(sale_id=sale_id, created_by_id=actor.id, **data.model_dump()))
    session.commit()
    session.expire_all()
    return get_sale(session, sale_id)


def remove_payment(session: Session, actor: UserAccount, sale_id: int, payment_id: int) -> Sale:
    payment = session.get(ClientPayment, payment_id)
    if payment is None or payment.sale_id != sale_id:
        raise NotFound()
    record_deletion(
        session,
        actor,
        kind=DeletionKind.CLIENT_PAYMENT,
        record_id=payment.id,
        sale_id=sale_id,
        description=payment.method,
        amount=payment.amount,
        occurred_on=payment.paid_on,
    )
    session.delete(payment)
    session.commit()
    session.expire_all()
    return get_sale(session, sale_id)
