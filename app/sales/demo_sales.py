"""Carga de las ventas de demostración. Va después de las cotizaciones de demostración. Crea la
venta, sus abonos y sus reservas con los servicios de la aplicación, para respetar sus reglas
(solo se vende una cotización aceptada, un abono no supera el saldo).

Repetible: una cotización que ya tiene venta se omite, y también una que no quedó aceptada (por
ejemplo, si alguien la devolvió a borrador en el entorno compartido).
"""

from datetime import timedelta
from decimal import Decimal
from functools import partial

from sqlalchemy import exists
from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.money import apply_percentage
from app.common.seeding import SeededRecord, seed_if_new
from app.quotes.models import Quote, QuoteStatus
from app.quotes.services.demo_quotes import find_demo_quote
from app.sales import booking_services
from app.sales.booking_services import BookingUpdate
from app.sales.demo_data import DEMO_SALES, DemoSale
from app.sales.models import Sale
from app.sales.schemas import PaymentCreate, SaleCreate
from app.sales.services import add_payment, create_sale


def _payment_amounts(total: int, demo: DemoSale) -> list[int]:
    # El último abono de una venta pagada es el resto, para que el redondeo no deje un peso.
    amounts = [apply_percentage(total, Decimal(payment.percent)) for payment in demo.payments]
    if sum(payment.percent for payment in demo.payments) == 100:
        amounts[-1] = total - sum(amounts[:-1])
    return amounts


def _create(session: Session, actor: UserAccount, quote: Quote, demo: DemoSale) -> None:
    sale = create_sale(session, actor, SaleCreate(quote_id=quote.id, notes=demo.notes))
    for payment, amount in zip(demo.payments, _payment_amounts(sale.total_price, demo)):
        add_payment(
            session,
            actor,
            sale.id,
            PaymentCreate(
                amount=amount,
                paid_on=today() + timedelta(days=payment.paid_in),
                method=payment.method,
                reference=payment.reference,
            ),
        )
    states = {booking.name: booking for booking in demo.bookings}
    for booking in booking_services.prepare(session, sale.id):
        demo_booking = states.get(booking.name)
        if demo_booking is not None:
            booking_services.update(
                session,
                booking.id,
                BookingUpdate(
                    status=demo_booking.status,
                    confirmation_code=demo_booking.confirmation_code,
                ),
            )


def seed_demo_sales(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_SALES:
        quote = find_demo_quote(session, demo.client_document, demo.destination)
        if quote is None:
            continue
        sold = exists().where(Sale.quote_id == Quote.id)
        records.append(
            seed_if_new(
                session,
                Quote,
                "Venta",
                f"{demo.destination} ({quote.client.display_name})",
                (Quote.id == quote.id) & (sold | (Quote.status != QuoteStatus.ACCEPTED)),
                partial(_create, session, actor, quote, demo),
            )
        )
    return records


def find_demo_sale(session: Session, client_document: tuple[str, str], destination: str):
    """La venta de la cotización de demostración, si la tiene."""
    quote = find_demo_quote(session, client_document, destination)
    if quote is None:
        return None
    return session.exec(select(Sale).where(Sale.quote_id == quote.id)).first()
