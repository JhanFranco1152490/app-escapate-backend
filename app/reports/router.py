from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.accounts.dependencies import CurrentUser, SessionDep, require_permission
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.reports import services
from app.reports.client_history import ClientHistory, client_history
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
_check_finance = require_permission("finance.view")
can_view_finance = Depends(_check_finance)
_ERRORS = error_responses(401, 403)
# Los reportes que traen datos de finanzas piden además ese permiso, como los indicadores
# financieros: sin él, ver reportes sería una puerta lateral a los gastos de la agencia.
_FINANCE_REPORTS = {ReportKind.EXPENSES}


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


# El historial va en la ficha del cliente, pero mezcla solicitudes, cotizaciones, ventas y pagos:
# pide el permiso de cada uno, no solo el de clientes. Sin alguno, la ficha no lo muestra.
@router.get(
    "/clients/{client_id}/history",
    dependencies=[
        Depends(require_permission(code))
        for code in ("clients.view", "travel_requests.view", "quotes.view", "sales.view")
    ],
    responses=error_responses(401, 403, 404),
)
def get_client_history(client_id: RecordId, session: SessionDep) -> ClientHistory:
    return client_history(session, client_id)


@router.get("/{kind}", dependencies=[can_view], responses=_ERRORS)
def report(
    kind: ReportKind, user: CurrentUser, session: SessionDep, period: Annotated[Period, Query()]
) -> Report:
    if kind in _FINANCE_REPORTS:
        _check_finance(user, session)
    return services.report(session, kind, period)
