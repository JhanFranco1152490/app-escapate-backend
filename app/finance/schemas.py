from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.common.fields import RecordId, required_text
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.finance.models import ExpenseCategory

Pesos = Annotated[int, Field(strict=True, ge=1, le=999_999_999_999)]


class ActualCostInput(InputSchema):
    description: Annotated[str, AfterValidator(required_text(150))]
    supplier_id: RecordId | None = None
    amount: Pesos
    paid_on: date | None = None


class CostSupplierRef(OutputSchema):
    id: int
    trade_name: str


class ActualCostOut(OutputSchema):
    id: int
    description: str
    supplier: CostSupplierRef | None
    amount: int
    paid_on: date | None


class Profitability(BaseModel):
    sale_price: int
    estimated_cost: int
    actual_cost: int
    # Pagado a los proveedores de lo real.
    paid_to_suppliers: int
    owed_to_suppliers: int
    # Con el costo real si ya hay alguno registrado; si no, con el estimado.
    profit: int
    margin_percent: Decimal | None
    uses_actual_cost: bool
    cost_difference: int
    costs: list[ActualCostOut]


class ExpenseInput(InputSchema):
    spent_on: date
    category: ExpenseCategory
    description: Annotated[str, AfterValidator(required_text(200))]
    amount: Pesos


class ExpenseOut(OutputSchema):
    id: int
    spent_on: date
    category: ExpenseCategory
    description: str
    amount: int
    created_by: UserRef


class PeriodFilters(BaseModel):
    date_from: date
    date_to: date


class MonthRow(BaseModel):
    month: str
    income: int
    supplier_payments: int
    operating_expenses: int
    net: int


class FinanceSummary(BaseModel):
    income: int
    supplier_payments: int
    operating_expenses: int
    expenses: int
    net: int
    by_month: list[MonthRow]
    by_category: dict[ExpenseCategory, int]
