from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.accounts.dependencies import SessionDep, require_permission
from app.audit import services
from app.audit.schemas import DeletionFilters, DeletionOut
from app.common.errors import error_responses
from app.common.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/api/audit", tags=["audit"])


# Quién borró un pago, un costo o un gasto es información de finanzas.
@router.get(
    "/deletions",
    dependencies=[Depends(require_permission("finance.view"))],
    responses=error_responses(401, 403),
)
def list_deletions(
    request: Request,
    session: SessionDep,
    filters: Annotated[DeletionFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[DeletionOut]:
    return services.list_deletions(session, filters, params, request)
