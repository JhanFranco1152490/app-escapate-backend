"""La venta (`Sale`) que sale de una cotización aceptada y los pagos del cliente
(`ClientPayment`).

La venta copia el precio y los datos del viaje al crearse: si después la cotización se ajusta,
lo vendido no cambia. El saldo y el estado del pago no se guardan, se calculan con los pagos.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Column, Text
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.codes import RecordCode
from app.common.columns import foreign_key, in_values, primary_key, timestamp
from app.quotes.models import Quote

SALE_CODE = RecordCode("VEN-")


class PaymentMethod(StrEnum):
    TRANSFER = "transfer"
    CASH = "cash"
    CARD = "card"
    OTHER = "other"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"


class Sale(SQLModel, table=True):
    __tablename__ = "sale"
    __table_args__ = (
        CheckConstraint("total_price > 0", name="ck_sale_total_price"),
        CheckConstraint("total_cost >= 0", name="ck_sale_total_cost"),
    )

    id: int | None = primary_key()
    # Una cotización se vende una sola vez.
    quote_id: int = foreign_key("quote.id", ondelete="RESTRICT", unique=True)
    client_id: int = foreign_key("client.id", ondelete="RESTRICT", index=True)
    destination: str = Field(max_length=150)
    departure_date: date | None = None
    return_date: date | None = None
    adults: int
    minors: int
    total_price: int = Field(sa_column=Column(BigInteger, nullable=False))
    # El costo estimado de la cotización al vender; el real se registra después.
    total_cost: int = Field(sa_column=Column(BigInteger, nullable=False))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()

    quote: Quote = Relationship()
    client: Client = Relationship()
    created_by: UserAccount = Relationship()
    payments: list["ClientPayment"] = Relationship(
        sa_relationship_kwargs={
            "order_by": "ClientPayment.paid_on, ClientPayment.id",
            "viewonly": True,
        }
    )

    @property
    def code(self) -> str:
        return SALE_CODE.format(self.id)

    @property
    def paid(self) -> int:
        return sum(payment.amount for payment in self.payments)

    @property
    def balance(self) -> int:
        return self.total_price - self.paid

    @property
    def payment_status(self) -> PaymentStatus:
        if self.paid == 0:
            return PaymentStatus.PENDING
        return PaymentStatus.PAID if self.balance <= 0 else PaymentStatus.PARTIAL


class ClientPayment(SQLModel, table=True):
    __tablename__ = "client_payment"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_client_payment_amount"),
        CheckConstraint(in_values("method", PaymentMethod), name="ck_client_payment_method"),
    )

    id: int | None = primary_key()
    sale_id: int = foreign_key("sale.id", ondelete="RESTRICT", index=True)
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    paid_on: date
    method: str = Field(max_length=10)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()

    created_by: UserAccount = Relationship()
