from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.suppliers import rate_schemas
from app.suppliers.rate_schemas import ServiceRateCreate, ServiceRateUpdate
from app.suppliers.services import (
    rate_management,
    rate_queries,
    tourist_service_management,
    tourist_service_queries,
)
from app.suppliers.tourist_service_schemas import (
    TouristServiceCreate,
    TouristServiceDetail,
    TouristServiceListItem,
    TouristServiceStatusChange,
    TouristServiceUpdate,
)

router = APIRouter(prefix="/api", tags=["tourist-services"])

can_view = Depends(require_permission("tourist_services.view"))
can_manage = Depends(require_permission("tourist_services.manage"))
Manager = Annotated[UserAccount, can_manage]
Paging = Annotated[PageParams, Depends(page_params)]


# --- Servicios -----------------------------------------------------------------------------


@router.get(
    "/suppliers/{supplier_id}/tourist-services",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def list_supplier_services(
    supplier_id: RecordId, request: Request, session: SessionDep, params: Paging
) -> Page[TouristServiceListItem]:
    return tourist_service_queries.list_supplier_services(session, supplier_id, params, request)


@router.post(
    "/suppliers/{supplier_id}/tourist-services",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
)
def create_tourist_service(
    supplier_id: RecordId, data: TouristServiceCreate, actor: Manager, session: SessionDep
) -> TouristServiceDetail:
    return tourist_service_management.create_tourist_service(session, actor, supplier_id, data)


@router.get(
    "/tourist-services/{service_id}",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def get_tourist_service(service_id: RecordId, session: SessionDep) -> TouristServiceDetail:
    return tourist_service_queries.get_tourist_service(session, service_id)


@router.put(
    "/tourist-services/{service_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_tourist_service(
    service_id: RecordId, data: TouristServiceUpdate, session: SessionDep
) -> TouristServiceDetail:
    return tourist_service_management.update_tourist_service(session, service_id, data)


@router.post(
    "/tourist-services/{service_id}/deactivate", responses=error_responses(401, 403, 404, 409)
)
def deactivate_tourist_service(
    service_id: RecordId, data: TouristServiceStatusChange, actor: Manager, session: SessionDep
) -> TouristServiceDetail:
    return tourist_service_management.deactivate_tourist_service(session, actor, service_id, data)


@router.post(
    "/tourist-services/{service_id}/activate",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def activate_tourist_service(
    service_id: RecordId, data: TouristServiceStatusChange, session: SessionDep
) -> TouristServiceDetail:
    return tourist_service_management.activate_tourist_service(session, service_id, data)


# --- Tarifas -------------------------------------------------------------------------------


@router.get(
    "/tourist-services/{service_id}/rates",
    dependencies=[can_view],
    responses=error_responses(401, 403, 404),
)
def list_service_rates(
    service_id: RecordId, request: Request, session: SessionDep, params: Paging
) -> Page[rate_schemas.ServiceRate]:
    return rate_queries.list_service_rates(session, service_id, params, request)


@router.post(
    "/tourist-services/{service_id}/rates",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
)
def create_service_rate(
    service_id: RecordId, data: ServiceRateCreate, actor: Manager, session: SessionDep
) -> rate_schemas.ServiceRate:
    return rate_management.create_service_rate(session, actor, service_id, data)


@router.put(
    "/tourist-services/{service_id}/rates/{rate_id}",
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def update_service_rate(
    service_id: RecordId, rate_id: RecordId, data: ServiceRateUpdate, session: SessionDep
) -> rate_schemas.ServiceRate:
    return rate_management.update_service_rate(session, service_id, rate_id, data)


@router.delete(
    "/tourist-services/{service_id}/rates/{rate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_manage],
    responses=error_responses(401, 403, 404, 409),
)
def delete_service_rate(
    service_id: RecordId,
    rate_id: RecordId,
    expected_version: Annotated[int, Query(ge=1)],
    session: SessionDep,
) -> None:
    rate_management.delete_service_rate(session, service_id, rate_id, expected_version)
