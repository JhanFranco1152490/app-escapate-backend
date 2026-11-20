from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.accounts.dependencies import SessionDep, require_permission
from app.accounts.models import UserAccount
from app.common.errors import error_responses
from app.common.fields import RecordId
from app.common.pagination import Page, PageParams, page_params
from app.quotes.schemas import (
    QuoteConditionsUpdate,
    QuoteCreate,
    QuoteDetail,
    QuoteFilters,
    QuoteGeneralUpdate,
    QuoteItemCreate,
    QuoteItemOut,
    QuoteItemUpdate,
    QuoteListItem,
    QuotePricingUpdate,
    QuoteTransition,
)
from app.quotes.services import quote_items, quote_management, quote_queries

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

can_view = Depends(require_permission("quotes.view"))
can_manage = Depends(require_permission("quotes.manage"))
Manager = Annotated[UserAccount, can_manage]

_WRITE_ERRORS = error_responses(401, 403, 404, 409)


@router.get("", dependencies=[can_view], responses=error_responses(401, 403))
def list_quotes(
    request: Request,
    session: SessionDep,
    filters: Annotated[QuoteFilters, Query()],
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[QuoteListItem]:
    return quote_queries.list_quotes(session, filters, params, request)


@router.get("/{quote_id}", dependencies=[can_view], responses=error_responses(401, 403, 404))
def get_quote(quote_id: RecordId, session: SessionDep) -> QuoteDetail:
    return quote_queries.get_quote(session, quote_id)


@router.post("", status_code=status.HTTP_201_CREATED, responses=_WRITE_ERRORS)
def create_quote(data: QuoteCreate, actor: Manager, session: SessionDep) -> QuoteDetail:
    return quote_management.create_quote(session, actor, data)


@router.put("/{quote_id}", dependencies=[can_manage], responses=_WRITE_ERRORS)
def update_quote(quote_id: RecordId, data: QuoteGeneralUpdate, session: SessionDep) -> QuoteDetail:
    return quote_management.update_general(session, quote_id, data)


@router.put("/{quote_id}/conditions", dependencies=[can_manage], responses=_WRITE_ERRORS)
def update_conditions(
    quote_id: RecordId, data: QuoteConditionsUpdate, session: SessionDep
) -> QuoteDetail:
    return quote_management.update_conditions(session, quote_id, data)


@router.put("/{quote_id}/pricing", dependencies=[can_manage], responses=_WRITE_ERRORS)
def update_pricing(
    quote_id: RecordId, data: QuotePricingUpdate, session: SessionDep
) -> QuoteDetail:
    return quote_management.update_pricing(session, quote_id, data)


@router.post("/{quote_id}/send", dependencies=[can_manage], responses=_WRITE_ERRORS)
def send_quote(quote_id: RecordId, data: QuoteTransition, session: SessionDep) -> QuoteDetail:
    return quote_management.send_quote(session, quote_id, data)


@router.post("/{quote_id}/return-to-draft", dependencies=[can_manage], responses=_WRITE_ERRORS)
def return_to_draft(quote_id: RecordId, data: QuoteTransition, session: SessionDep) -> QuoteDetail:
    return quote_management.return_to_draft(session, quote_id, data)


@router.post("/{quote_id}/accept", dependencies=[can_manage], responses=_WRITE_ERRORS)
def accept_quote(quote_id: RecordId, data: QuoteTransition, session: SessionDep) -> QuoteDetail:
    return quote_management.accept_quote(session, quote_id, data)


@router.post("/{quote_id}/reject", dependencies=[can_manage], responses=_WRITE_ERRORS)
def reject_quote(quote_id: RecordId, data: QuoteTransition, session: SessionDep) -> QuoteDetail:
    return quote_management.reject_quote(session, quote_id, data)


@router.post(
    "/{quote_id}/items",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_manage],
    responses=_WRITE_ERRORS,
)
def add_item(quote_id: RecordId, data: QuoteItemCreate, session: SessionDep) -> QuoteItemOut:
    return quote_items.add_item(session, quote_id, data)


@router.put("/{quote_id}/items/{item_id}", dependencies=[can_manage], responses=_WRITE_ERRORS)
def update_item(
    quote_id: RecordId, item_id: RecordId, data: QuoteItemUpdate, session: SessionDep
) -> QuoteItemOut:
    return quote_items.update_item(session, quote_id, item_id, data)


@router.delete(
    "/{quote_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_manage],
    responses=_WRITE_ERRORS,
)
def remove_item(quote_id: RecordId, item_id: RecordId, session: SessionDep) -> None:
    quote_items.remove_item(session, quote_id, item_id)
