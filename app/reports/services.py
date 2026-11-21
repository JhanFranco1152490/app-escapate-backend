"""Dashboard, indicadores y reportes: solo lecturas sobre los demás dominios."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, func
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.dates import BOGOTA, today
from app.finance.models import ActualCost, OperatingExpense
from app.quotes.follow_up_models import FollowUpStatus, QuoteFollowUp
from app.quotes.models import Quote, QuoteItem, QuoteStatus
from app.reports.schemas import (
    CommercialIndicators,
    Dashboard,
    FinancialIndicators,
    Period,
    RankRow,
    Report,
    ReportKind,
)
from app.sales.booking_models import Booking, BookingStatus
from app.sales.models import ClientPayment, Sale
from app.suppliers.service_types import SERVICE_TYPE_LABELS, ServiceType
from app.travel_requests.models import PENDING_STATUSES, TravelRequest

_TOP = 5


def _count(session: Session, model, *conditions) -> int:
    return session.exec(select(func.count()).select_from(model).where(*conditions)).one()


def _sum(session: Session, column, *conditions) -> int:
    return int(session.exec(select(func.coalesce(func.sum(column), 0)).where(*conditions)).one())


def _created_in(column, period: Period):
    # Las marcas de tiempo se comparan con los días de Bogotá del período, completos.
    start = datetime.combine(period.date_from, time.min, BOGOTA)
    end = datetime.combine(period.date_to + timedelta(days=1), time.min, BOGOTA)
    return and_(column >= start, column < end)


def _percent(part: int, whole: int) -> Decimal | None:
    if not whole:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.01"))


def _receivable(session: Session) -> int:
    return _sum(session, Sale.total_price) - _sum(session, ClientPayment.amount)


def dashboard(session: Session) -> Dashboard:
    day = today()
    sent = col(Quote.status) == QuoteStatus.SENT
    pending_follow_up = col(QuoteFollowUp.status) == FollowUpStatus.PENDING
    return Dashboard(
        pending_requests=_count(
            session, TravelRequest, col(TravelRequest.status).in_(PENDING_STATUSES)
        ),
        quotes_draft=_count(session, Quote, col(Quote.status) == QuoteStatus.DRAFT),
        quotes_sent=_count(session, Quote, sent, col(Quote.valid_until) >= day),
        quotes_expired=_count(session, Quote, sent, col(Quote.valid_until) < day),
        follow_ups_red=_count(
            session, QuoteFollowUp, pending_follow_up, col(QuoteFollowUp.due_date) < day
        ),
        follow_ups_yellow=_count(
            session,
            QuoteFollowUp,
            pending_follow_up,
            col(QuoteFollowUp.due_date) >= day,
            col(QuoteFollowUp.due_date) <= day + timedelta(days=1),
        ),
        bookings_to_request=_count(
            session, Booking, col(Booking.status) == BookingStatus.TO_REQUEST
        ),
        trips_next_30_days=_count(
            session,
            Sale,
            col(Sale.departure_date) >= day,
            col(Sale.departure_date) <= day + timedelta(days=30),
        ),
        receivable=_receivable(session),
    )


def _rank(rows) -> list[RankRow]:
    ranked = sorted(rows, key=lambda row: (-row[2], -row[1], row[0]))
    return [RankRow(label=label, count=count, amount=amount) for label, count, amount in ranked]


def commercial(session: Session, period: Period) -> CommercialIndicators:
    sold = _created_in(col(Sale.created_at), period)
    decided = _created_in(col(Quote.decided_at), period)
    accepted = _count(session, Quote, decided, col(Quote.status) == QuoteStatus.ACCEPTED)
    rejected = _count(session, Quote, decided, col(Quote.status) == QuoteStatus.REJECTED)
    sales_count = _count(session, Sale, sold)
    sales_amount = _sum(session, Sale.total_price, sold)

    destinations = session.exec(
        select(Sale.destination, func.count(), func.sum(Sale.total_price))
        .where(sold)
        .group_by(Sale.destination)
    ).all()
    advisors = session.exec(
        select(
            UserAccount.first_name, UserAccount.last_name, func.count(), func.sum(Sale.total_price)
        )
        .join(UserAccount, UserAccount.id == Sale.created_by_id)
        .where(sold)
        .group_by(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
    ).all()
    # Cuántos servicios de cada tipo se vendieron.
    service_types = session.exec(
        select(QuoteItem.service_type, func.count())
        .join(Sale, Sale.quote_id == QuoteItem.quote_id)
        .where(sold, ~col(QuoteItem.is_optional))
        .group_by(QuoteItem.service_type)
    ).all()

    return CommercialIndicators(
        requests_received=_count(
            session, TravelRequest, _created_in(col(TravelRequest.created_at), period)
        ),
        quotes_created=_count(session, Quote, _created_in(col(Quote.created_at), period)),
        quotes_accepted=accepted,
        quotes_rejected=rejected,
        conversion_percent=_percent(accepted, accepted + rejected),
        sales_count=sales_count,
        sales_amount=sales_amount,
        average_ticket=sales_amount // sales_count if sales_count else None,
        new_clients=_count(session, Client, _created_in(col(Client.created_at), period)),
        top_destinations=_rank(destinations)[:_TOP],
        sales_by_advisor=_rank(
            (f"{first} {last}", count, int(amount)) for first, last, count, amount in advisors
        ),
        sales_by_service_type=sorted(
            (
                RankRow(label=SERVICE_TYPE_LABELS[ServiceType(kind)], count=count, amount=0)
                for kind, count in service_types
            ),
            key=lambda row: -row.count,
        ),
    )


def financial(session: Session, period: Period) -> FinancialIndicators:
    sold = _created_in(col(Sale.created_at), period)
    sales_amount = _sum(session, Sale.total_price, sold)
    # Ganancia de lo vendido en el período: costo real si se registró, si no el estimado.
    sales = session.exec(select(Sale.id, Sale.total_price, Sale.total_cost).where(sold)).all()
    actual = dict(
        session.exec(
            select(ActualCost.sale_id, func.sum(ActualCost.amount)).group_by(ActualCost.sale_id)
        ).all()
    )
    profit = sum(price - int(actual.get(sale_id, cost)) for sale_id, price, cost in sales)
    in_period = (period.date_from, period.date_to)
    income = _sum(session, ClientPayment.amount, col(ClientPayment.paid_on).between(*in_period))
    supplier = _sum(session, ActualCost.amount, col(ActualCost.paid_on).between(*in_period))
    operating = _sum(
        session, OperatingExpense.amount, col(OperatingExpense.spent_on).between(*in_period)
    )
    return FinancialIndicators(
        sales_amount=sales_amount,
        estimated_profit=profit,
        margin_percent=_percent(profit, sales_amount),
        income=income,
        expenses=supplier + operating,
        net=income - supplier - operating,
        receivable=_receivable(session),
        payable=_sum(session, ActualCost.amount, col(ActualCost.paid_on).is_(None)),
    )


def _day(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.astimezone(BOGOTA).date()
    return value.isoformat()


def report(session: Session, kind: ReportKind, period: Period) -> Report:
    if kind == ReportKind.SALES:
        rows = session.exec(
            select(Sale).where(_created_in(col(Sale.created_at), period)).order_by(Sale.id)
        ).all()
        return Report(
            title="Ventas",
            columns=["Venta", "Fecha", "Cliente", "Destino", "Salida", "Total", "Pagado", "Saldo"],
            rows=[
                [
                    sale.code,
                    _day(sale.created_at),
                    sale.client.display_name,
                    sale.destination,
                    _day(sale.departure_date),
                    sale.total_price,
                    sale.paid,
                    sale.balance,
                ]
                for sale in rows
            ],
        )
    if kind == ReportKind.PAYMENTS:
        rows = session.exec(
            select(ClientPayment, Sale)
            .join(Sale, Sale.id == ClientPayment.sale_id)
            .where(col(ClientPayment.paid_on).between(period.date_from, period.date_to))
            .order_by(ClientPayment.paid_on, ClientPayment.id)
        ).all()
        return Report(
            title="Pagos de clientes",
            columns=["Fecha", "Venta", "Cliente", "Valor", "Medio", "Referencia"],
            rows=[
                [
                    _day(payment.paid_on),
                    sale.code,
                    sale.client.display_name,
                    payment.amount,
                    payment.method,
                    payment.reference,
                ]
                for payment, sale in rows
            ],
        )
    if kind == ReportKind.QUOTES:
        rows = session.exec(
            select(Quote).where(_created_in(col(Quote.created_at), period)).order_by(Quote.id)
        ).all()
        return Report(
            title="Cotizaciones",
            columns=["Cotización", "Fecha", "Cliente", "Destino", "Estado", "Precio", "Asesor"],
            rows=[
                [
                    quote.code,
                    _day(quote.created_at),
                    quote.client.display_name,
                    quote.destination,
                    "expired" if quote.is_expired else quote.status,
                    quote.totals.sale,
                    quote.created_by.full_name,
                ]
                for quote in rows
            ],
        )
    if kind == ReportKind.EXPENSES:
        rows = session.exec(
            select(OperatingExpense)
            .where(col(OperatingExpense.spent_on).between(period.date_from, period.date_to))
            .order_by(OperatingExpense.spent_on)
        ).all()
        return Report(
            title="Gastos operativos",
            columns=["Fecha", "Categoría", "Descripción", "Valor"],
            rows=[[_day(row.spent_on), row.category, row.description, row.amount] for row in rows],
        )
    rows = session.exec(
        select(TravelRequest)
        .where(_created_in(col(TravelRequest.created_at), period))
        .order_by(TravelRequest.id)
    ).all()
    return Report(
        title="Solicitudes de viaje",
        columns=["Solicitud", "Fecha", "Cliente", "Destino", "Estado", "Asesor"],
        rows=[
            [
                request.code,
                _day(request.created_at),
                request.client.display_name,
                request.destination,
                request.status,
                request.assigned_to.full_name,
            ]
            for request in rows
        ],
    )
