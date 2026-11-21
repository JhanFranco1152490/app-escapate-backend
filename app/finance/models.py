"""Lo financiero: costos reales de cada venta (lo que se le paga a los proveedores) y gastos
operativos de la agencia. Ingresos, egresos y rentabilidad se calculan, no se guardan."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Column
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.columns import foreign_key, in_values, primary_key, timestamp
from app.sales.models import Sale
from app.suppliers.models import Supplier


class ExpenseCategory(StrEnum):
    RENT = "rent"
    PAYROLL = "payroll"
    MARKETING = "marketing"
    UTILITIES = "utilities"
    TAXES = "taxes"
    SOFTWARE = "software"
    OTHER = "other"


class ActualCost(SQLModel, table=True):
    """Un costo real de una venta. Sin `paid_on`, todavía se le debe al proveedor."""

    __tablename__ = "actual_cost"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_actual_cost_amount"),)

    id: int | None = primary_key()
    sale_id: int = foreign_key("sale.id", ondelete="RESTRICT", index=True)
    supplier_id: int | None = foreign_key("supplier.id", ondelete="RESTRICT", nullable=True)
    description: str = Field(max_length=150)
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    paid_on: date | None = Field(default=None, index=True)
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()

    sale: Sale = Relationship()
    supplier: Supplier | None = Relationship()


class OperatingExpense(SQLModel, table=True):
    __tablename__ = "operating_expense"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_operating_expense_amount"),
        CheckConstraint(
            in_values("category", ExpenseCategory), name="ck_operating_expense_category"
        ),
    )

    id: int | None = primary_key()
    spent_on: date = Field(index=True)
    category: str = Field(max_length=12)
    description: str = Field(max_length=200)
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()

    created_by: UserAccount = Relationship()
