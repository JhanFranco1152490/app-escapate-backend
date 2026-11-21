from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.quotes.package_schemas import (
    PackageCreate,
    PackageDetail,
    PackageFilters,
    PackageListItem,
    PackageUpdate,
    QuoteFromPackage,
)
from app.quotes.schemas import QuoteDetail, QuoteItemCreate, QuoteItemOut, QuoteItemUpdate
from app.quotes.services import packages

router = APIRouter(prefix="/api", tags=["packages"])

can_view = Depends(require_permission("quotes.view"))
can_manage = Depends(require_permission("quotes.manage"))
Manager = Annotated[UserAccount, can_manage]
_WRITE = error_responses(401, 403, 404, 409)


@router.get("/packages", dependencies=[can_view], responses=error_responses(401, 403))
def list_packages(
    request: Request,
    session: SessionDep,
    filters: Annotated[PackageFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[PackageListItem]:
    return packages.list_packages(session, filters, params, request)


@router.get("/packages/{package_id}", dependencies=[can_view], responses=_WRITE)
def get_package(package_id: RecordId, session: SessionDep) -> PackageDetail:
    return packages.get_package(session, package_id)


@router.post("/packages", status_code=status.HTTP_201_CREATED, responses=_WRITE)
def create_package(data: PackageCreate, actor: Manager, session: SessionDep) -> PackageDetail:
    return packages.create_package(session, actor, data)


@router.put("/packages/{package_id}", dependencies=[can_manage], responses=_WRITE)
def update_package(
    package_id: RecordId, data: PackageUpdate, session: SessionDep
) -> PackageDetail:
    return packages.update_package(session, package_id, data)


@router.post(
    "/packages/{package_id}/items",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_manage],
    responses=_WRITE,
)
def add_package_item(
    package_id: RecordId, data: QuoteItemCreate, session: SessionDep
) -> QuoteItemOut:
    return packages.add_item(session, package_id, data)


@router.put("/packages/{package_id}/items/{item_id}", dependencies=[can_manage], responses=_WRITE)
def update_package_item(
    package_id: RecordId, item_id: RecordId, data: QuoteItemUpdate, session: SessionDep
) -> QuoteItemOut:
    return packages.update_item(session, package_id, item_id, data)


@router.delete(
    "/packages/{package_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_manage],
    responses=_WRITE,
)
def remove_package_item(package_id: RecordId, item_id: RecordId, session: SessionDep) -> None:
    packages.remove_item(session, package_id, item_id)


@router.post("/quotes/from-package", status_code=status.HTTP_201_CREATED, responses=_WRITE)
def quote_from_package(data: QuoteFromPackage, actor: Manager, session: SessionDep) -> QuoteDetail:
    return packages.quote_from_package(session, actor, data)
