from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.accounts.dependencies import SessionDep, require_permission
from app.common.errors import error_responses
from app.reports import services
from app.reports.schemas import (
    CommercialIndicators,
    Dashboard,
    FinancialIndicators,
    Period,
    Report,
    ReportKind,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

can_view = Depends(require_permission("reports.view"))
can_view_finance = Depends(require_permission("finance.view"))
_ERRORS = error_responses(401, 403)


@router.get("/dashboard", dependencies=[can_view], responses=_ERRORS)
def dashboard(session: SessionDep) -> Dashboard:
    return services.dashboard(session)


@router.get("/commercial", dependencies=[can_view], responses=_ERRORS)
def commercial(session: SessionDep, period: Annotated[Period, Query()]) -> CommercialIndicators:
    return services.commercial(session, period)


# Los indicadores financieros piden además el permiso de finanzas: muestran la ganancia.
@router.get("/financial", dependencies=[can_view, can_view_finance], responses=_ERRORS)
def financial(session: SessionDep, period: Annotated[Period, Query()]) -> FinancialIndicators:
    return services.financial(session, period)


@router.get("/{kind}", dependencies=[can_view], responses=_ERRORS)
def report(kind: ReportKind, session: SessionDep, period: Annotated[Period, Query()]) -> Report:
    return services.report(session, kind, period)
