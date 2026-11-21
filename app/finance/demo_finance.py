"""Carga de los costos reales y los gastos de operación de demostración. Los costos van después
de las ventas de demostración.

Repetible: una venta que ya tiene costos reales se omite entera, y un gasto con la misma
descripción también (sus fechas son relativas a hoy: cargarlo otro día lo duplicaría).
"""

from datetime import timedelta
from functools import partial

from sqlalchemy import exists
from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.common.dates import today
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.finance.demo_data import DEMO_EXPENSES, DEMO_SALE_COSTS, DemoExpense, DemoSaleCosts
from app.finance.models import ActualCost, OperatingExpense
from app.finance.schemas import ActualCostInput, ExpenseInput
from app.finance.services import add_cost, add_expense
from app.sales.demo_sales import find_demo_sale
from app.sales.models import Sale
from app.suppliers.models import Supplier


def _create_costs(session: Session, actor: UserAccount, sale: Sale, demo: DemoSaleCosts) -> None:
    for cost in demo.costs:
        supplier_id = None
        if cost.supplier_document is not None:
            supplier_id = session.exec(
                select(Supplier.id).where(same_document(Supplier, *cost.supplier_document))
            ).one()
        paid_on = None if cost.paid_in is None else today() + timedelta(days=cost.paid_in)
        add_cost(
            session,
            actor,
            sale.id,
            ActualCostInput(
                description=cost.description,
                supplier_id=supplier_id,
                amount=cost.amount,
                paid_on=paid_on,
            ),
        )


def _create_expense(session: Session, actor: UserAccount, demo: DemoExpense) -> None:
    add_expense(
        session,
        actor,
        ExpenseInput(
            spent_on=today() + timedelta(days=demo.spent_in),
            category=demo.category,
            description=demo.description,
            amount=demo.amount,
        ),
    )


def seed_demo_finance(session: Session, actor: UserAccount) -> list[SeededRecord]:
    records = []
    for demo in DEMO_SALE_COSTS:
        sale = find_demo_sale(session, demo.client_document, demo.destination)
        if sale is None:
            continue
        records.append(
            seed_if_new(
                session,
                Sale,
                "Costos reales",
                f"{demo.destination} ({sale.client.display_name})",
                (Sale.id == sale.id) & exists().where(ActualCost.sale_id == Sale.id),
                partial(_create_costs, session, actor, sale, demo),
            )
        )
    records += [
        seed_if_new(
            session,
            OperatingExpense,
            "Gasto",
            demo.description,
            OperatingExpense.description == demo.description,
            partial(_create_expense, session, actor, demo),
        )
        for demo in DEMO_EXPENSES
    ]
    return records
