"""Constancia de lo que se borra de verdad: quién quitó un pago, un costo o un gasto."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Column
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.columns import foreign_key, in_values, primary_key, timestamp


class DeletionKind(StrEnum):
    CLIENT_PAYMENT = "client_payment"
    ACTUAL_COST = "actual_cost"
    OPERATING_EXPENSE = "operating_expense"


class DeletionRecord(SQLModel, table=True):
    """Lo que había en la fila borrada, sin textos libres que puedan traer datos personales.

    `record_id` y `sale_id` son enteros sin clave foránea: la fila a la que apuntaban ya no
    existe, y atar este registro a la tabla de ventas obligaría a este dominio a depender de
    quienes lo usan.
    """

    __tablename__ = "deletion_record"
    __table_args__ = (CheckConstraint(in_values("kind", DeletionKind), name="ck_deletion_kind"),)

    id: int | None = primary_key()
    kind: str = Field(max_length=17)
    record_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    sale_id: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    description: str = Field(max_length=200)
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    occurred_on: date | None = Field(default=None)
    deleted_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    deleted_at: datetime | None = timestamp(index=True)

    deleted_by: UserAccount = Relationship()
