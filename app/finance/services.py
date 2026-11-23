"""Costos reales, rentabilidad por venta, gastos operativos e ingresos y egresos."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import Request
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.accounts.models import UserAccount
from app.audit.models import DeletionKind
from app.audit.services import record_deletion
from app.common.errors import InvalidFields, NotFound
from app.common.pagination import Page, PageParams, paginate
from app.finance.models import ActualCost, ExpenseCategory, OperatingExpense
from app.finance.schemas import (
    ActualCostInput,
    ExpenseInput,
    FinanceSummary,
    MonthRow,
    PeriodFilters,
    Profitability,
)
from app.sales.models import ClientPayment, Sale
from app.suppliers.models import Supplier


def _sale(session: Session, sale_id: int) -> Sale:
    sale = session.get(Sale, sale_id)
    if sale is None:
        raise NotFound()
    return sale


def _check_supplier(session: Session, data: ActualCostInput) -> None:
    if data.supplier_id is not None and session.get(Supplier, data.supplier_id) is None:
        raise InvalidFields(fields={"supplier_id": ["El proveedor no existe."]})


def profitability(session: Session, sale_id: int) -> Profitability:
    sale = _sale(session, sale_id)
    costs = session.exec(
        select(ActualCost)
        .where(ActualCost.sale_id == sale.id)
        .options(joinedload(ActualCost.supplier))
        .order_by(col(ActualCost.id))
    ).all()
    actual = sum(cost.amount for cost in costs)
    paid = sum(cost.amount for cost in costs if cost.paid_on is not None)
    uses_actual = bool(costs)
    cost = actual if uses_actual else sale.total_cost
    profit = sale.total_price - cost
    margin = (
        (Decimal(profit) * 100 / Decimal(sale.total_price)).quantize(Decimal("0.01"))
        if sale.total_price
        else None
    )
    return Profitability(
        sale_price=sale.total_price,
        estimated_cost=sale.total_cost,
        actual_cost=actual,
        paid_to_suppliers=paid,
        owed_to_suppliers=actual - paid,
        profit=profit,
        margin_percent=margin,
        uses_actual_cost=uses_actual,
        cost_difference=actual - sale.total_cost if uses_actual else 0,
        costs=costs,
    )


def add_cost(
    session: Session, actor: UserAccount, sale_id: int, data: ActualCostInput
) -> Profitability:
    _sale(session, sale_id)
    _check_supplier(session, data)
    session.add(ActualCost(sale_id=sale_id, created_by_id=actor.id, **data.model_dump()))
    session.commit()
    return profitability(session, sale_id)


def update_cost(session: Session, cost_id: int, data: ActualCostInput) -> Profitability:
    cost = session.get(ActualCost, cost_id)
    if cost is None:
        raise NotFound()
    _check_supplier(session, data)
    for name, value in data.model_dump().items():
        setattr(cost, name, value)
    session.add(cost)
    session.commit()
    return profitability(session, cost.sale_id)


def remove_cost(session: Session, actor: UserAccount, cost_id: int) -> Profitability:
    cost = session.get(ActualCost, cost_id)
    if cost is None:
        raise NotFound()
    sale_id = cost.sale_id
    record_deletion(
        session,
        actor,
        kind=DeletionKind.ACTUAL_COST,
        record_id=cost.id,
        sale_id=sale_id,
        description=cost.description,
        amount=cost.amount,
        occurred_on=cost.paid_on,
    )
    session.delete(cost)
    session.commit()
    return profitability(session, sale_id)


def list_expenses(
    session: Session, period: PeriodFilters, params: PageParams, request: Request
) -> Page:
    statement = (
        select(OperatingExpense)
        .where(
            col(OperatingExpense.spent_on) >= period.date_from,
            col(OperatingExpense.spent_on) <= period.date_to,
        )
        .options(joinedload(OperatingExpense.created_by))
        .order_by(col(OperatingExpense.spent_on).desc(), col(OperatingExpense.id).desc())
    )
    return paginate(session, statement, params, request)


def add_expense(session: Session, actor: UserAccount, data: ExpenseInput) -> OperatingExpense:
    expense = OperatingExpense(created_by_id=actor.id, **data.model_dump())
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


def remove_expense(session: Session, actor: UserAccount, expense_id: int) -> None:
    expense = session.get(OperatingExpense, expense_id)
    if expense is None:
        raise NotFound()
    record_deletion(
        session,
        actor,
        kind=DeletionKind.OPERATING_EXPENSE,
        record_id=expense.id,
        description=expense.description,
        amount=expense.amount,
        occurred_on=expense.spent_on,
    )
    session.delete(expense)
    session.commit()


def _month(day: date) -> str:
    return day.strftime("%Y-%m")


def summary(session: Session, period: PeriodFilters) -> FinanceSummary:
    """Caja del período: lo que entró de los clientes y lo que salió a proveedores y en gastos
    de la agencia, por fecha de pago."""
    start, end = period.date_from, period.date_to
    income = session.exec(
        select(ClientPayment.paid_on, ClientPayment.amount).where(
            col(ClientPayment.paid_on) >= start, col(ClientPayment.paid_on) <= end
        )
    ).all()
    supplier = session.exec(
        select(ActualCost.paid_on, ActualCost.amount).where(
            col(ActualCost.paid_on) >= start, col(ActualCost.paid_on) <= end
        )
    ).all()
    expenses = session.exec(
        select(
            OperatingExpense.spent_on, OperatingExpense.category, OperatingExpense.amount
        ).where(col(OperatingExpense.spent_on) >= start, col(OperatingExpense.spent_on) <= end)
    ).all()

    months: dict[str, dict[str, int]] = defaultdict(
        lambda: {"income": 0, "supplier_payments": 0, "operating_expenses": 0}
    )
    for day, amount in income:
        months[_month(day)]["income"] += amount
    for day, amount in supplier:
        months[_month(day)]["supplier_payments"] += amount
    by_category = {category: 0 for category in ExpenseCategory}
    for day, category, amount in expenses:
        months[_month(day)]["operating_expenses"] += amount
        by_category[ExpenseCategory(category)] += amount

    rows = [
        MonthRow(
            month=month,
            net=values["income"] - values["supplier_payments"] - values["operating_expenses"],
            **values,
        )
        for month, values in sorted(months.items())
    ]
    total_income = sum(row.income for row in rows)
    total_supplier = sum(row.supplier_payments for row in rows)
    total_expenses = sum(row.operating_expenses for row in rows)
    return FinanceSummary(
        income=total_income,
        supplier_payments=total_supplier,
        operating_expenses=total_expenses,
        expenses=total_supplier + total_expenses,
        net=total_income - total_supplier - total_expenses,
        by_month=rows,
        by_category=by_category,
    )
