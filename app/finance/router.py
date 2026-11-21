from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.finance import services
from app.finance.schemas import (
    ActualCostInput,
    ExpenseInput,
    ExpenseOut,
    FinanceSummary,
    PeriodFilters,
    Profitability,
)

router = APIRouter(prefix="/api", tags=["finance"])

can_view = Depends(require_permission("finance.view"))
Manager = Annotated[UserAccount, Depends(require_permission("finance.manage"))]
_READ = error_responses(401, 403, 404)
_WRITE = error_responses(401, 403, 404)


@router.get("/sales/{sale_id}/profitability", dependencies=[can_view], responses=_READ)
def profitability(sale_id: RecordId, session: SessionDep) -> Profitability:
    return services.profitability(session, sale_id)


@router.post("/sales/{sale_id}/costs", status_code=status.HTTP_201_CREATED, responses=_WRITE)
def add_cost(
    sale_id: RecordId, data: ActualCostInput, actor: Manager, session: SessionDep
) -> Profitability:
    return services.add_cost(session, actor, sale_id, data)


@router.put("/costs/{cost_id}", responses=_WRITE)
def update_cost(
    cost_id: RecordId, data: ActualCostInput, actor: Manager, session: SessionDep
) -> Profitability:
    return services.update_cost(session, cost_id, data)


@router.delete("/costs/{cost_id}", responses=_WRITE)
def remove_cost(cost_id: RecordId, actor: Manager, session: SessionDep) -> Profitability:
    return services.remove_cost(session, cost_id)


@router.get("/expenses", dependencies=[can_view], responses=_READ)
def list_expenses(
    request: Request,
    session: SessionDep,
    period: Annotated[PeriodFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[ExpenseOut]:
    return services.list_expenses(session, period, params, request)


@router.post("/expenses", status_code=status.HTTP_201_CREATED, responses=_WRITE)
def add_expense(data: ExpenseInput, actor: Manager, session: SessionDep) -> ExpenseOut:
    return services.add_expense(session, actor, data)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_WRITE)
def remove_expense(expense_id: RecordId, actor: Manager, session: SessionDep) -> None:
    services.remove_expense(session, expense_id)


@router.get("/finance/summary", dependencies=[can_view], responses=_READ)
def finance_summary(
    session: SessionDep, period: Annotated[PeriodFilters, Query()]
) -> FinanceSummary:
    return services.summary(session, period)
