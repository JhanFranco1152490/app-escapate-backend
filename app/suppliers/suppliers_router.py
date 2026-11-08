from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.suppliers.schemas import (
    SupplierCreate,
    SupplierDetail,
    SupplierFilters,
    SupplierListItem,
    SupplierStatusChange,
    SupplierUpdate,
)
from app.suppliers.services import supplier_management, supplier_queries

router = APIRouter(prefix="/api", tags=["suppliers"])

can_view = Depends(require_permission("suppliers.view"))
can_manage = Depends(require_permission("suppliers.manage"))
Manager = Annotated[UserAccount, can_manage]


@router.get("/suppliers", dependencies=[can_view], responses=error_responses(401, 403))
def list_suppliers(
    request: Request,
    session: SessionDep,
    filters: Annotated[SupplierFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[SupplierListItem]:
    return supplier_queries.list_suppliers(session, filters, params, request)


@router.get(
    "/suppliers/{supplier_id}", dependencies=[can_view], responses=error_responses(401, 403, 404)
)
def get_supplier(supplier_id: RecordId, session: SessionDep) -> SupplierDetail:
    return supplier_queries.get_supplier(session, supplier_id)


@router.post(
    "/suppliers", status_code=status.HTTP_201_CREATED, responses=error_responses(401, 403)
)
def create_supplier(data: SupplierCreate, actor: Manager, session: SessionDep) -> SupplierDetail:
    return supplier_management.create_supplier(session, actor, data)


@router.put(
    "/suppliers/{supplier_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_supplier(
    supplier_id: RecordId, data: SupplierUpdate, session: SessionDep
) -> SupplierDetail:
    return supplier_management.update_supplier(session, supplier_id, data)


@router.post("/suppliers/{supplier_id}/deactivate", responses=error_responses(401, 403, 404, 409))
def deactivate_supplier(
    supplier_id: RecordId, data: SupplierStatusChange, actor: Manager, session: SessionDep
) -> SupplierDetail:
    return supplier_management.deactivate_supplier(session, actor, supplier_id, data)


@router.post(
    "/suppliers/{supplier_id}/activate",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def activate_supplier(
    supplier_id: RecordId, data: SupplierStatusChange, session: SessionDep
) -> SupplierDetail:
    return supplier_management.activate_supplier(session, supplier_id, data)
