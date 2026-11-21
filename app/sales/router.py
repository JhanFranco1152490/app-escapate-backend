from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.sales import booking_services, services
from app.sales.schemas import PaymentCreate, SaleCreate, SaleDetail, SaleFilters, SaleListItem

router = APIRouter(prefix="/api/sales", tags=["sales"])

can_view = Depends(require_permission("sales.view"))
Manager = Annotated[UserAccount, Depends(require_permission("sales.manage"))]
_WRITE_ERRORS = error_responses(401, 403, 404, 409)


@router.get("", dependencies=[can_view], responses=error_responses(401, 403))
def list_sales(
    request: Request,
    session: SessionDep,
    filters: Annotated[SaleFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[SaleListItem]:
    return services.list_sales(session, filters, params, request)


@router.get("/{sale_id}", dependencies=[can_view], responses=error_responses(401, 403, 404))
def get_sale(sale_id: RecordId, session: SessionDep) -> SaleDetail:
    return services.get_sale(session, sale_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=_WRITE_ERRORS)
def create_sale(data: SaleCreate, actor: Manager, session: SessionDep) -> SaleDetail:
    return services.create_sale(session, actor, data)


@router.post("/{sale_id}/payments", status_code=status.HTTP_201_CREATED, responses=_WRITE_ERRORS)
def add_payment(
    sale_id: RecordId, data: PaymentCreate, actor: Manager, session: SessionDep
) -> SaleDetail:
    return services.add_payment(session, actor, sale_id, data)


@router.delete("/{sale_id}/payments/{payment_id}", responses=_WRITE_ERRORS)
def remove_payment(
    sale_id: RecordId, payment_id: RecordId, actor: Manager, session: SessionDep
) -> SaleDetail:
    return services.remove_payment(session, sale_id, payment_id)


# --- Reservas ------------------------------------------------------------------------------

bookings_router = APIRouter(prefix="/api", tags=["bookings"])


@bookings_router.get("/bookings", dependencies=[can_view], responses=error_responses(401, 403))
def list_bookings(
    request: Request,
    session: SessionDep,
    filters: Annotated[booking_services.BookingFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[booking_services.BookingOut]:
    return booking_services.list_bookings(session, filters, params, request)


@bookings_router.post("/sales/{sale_id}/bookings/prepare", responses=_WRITE_ERRORS)
def prepare_bookings(
    sale_id: RecordId, actor: Manager, session: SessionDep
) -> list[booking_services.BookingOut]:
    return booking_services.prepare(session, sale_id)


@bookings_router.put("/bookings/{booking_id}", responses=_WRITE_ERRORS)
def update_booking(
    booking_id: RecordId,
    data: booking_services.BookingUpdate,
    actor: Manager,
    session: SessionDep,
) -> booking_services.BookingOut:
    return booking_services.update(session, booking_id, data)
