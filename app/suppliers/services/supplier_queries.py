"""Lecturas de proveedores: lista con búsqueda y filtros, y ficha."""

from fastapi import Request
from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, map_results, paginate
from app.common.search import contains, folded, has_every_word, name_or_document
from app.suppliers.models import Supplier
from app.suppliers.schemas import SupplierFilters, SupplierListItem, SupplierStatusFilter
from app.suppliers.tourist_service_models import TouristService

# Las palabras pueden estar en el nombre comercial o en la razón social, que suele ser otra.
_names = col(Supplier.trade_name) + " " + func.coalesce(col(Supplier.legal_name), "")

_active_services = (
    select(func.count())
    .select_from(TouristService)
    .where(TouristService.supplier_id == Supplier.id, col(TouristService.is_active))
    .correlate(Supplier)
    .scalar_subquery()
)


def _list_item(row) -> SupplierListItem:
    supplier, active_service_count = row
    return SupplierListItem.model_validate(supplier).model_copy(
        update={"active_service_count": active_service_count}
    )


def _search(text: str) -> ColumnElement[bool]:
    conditions = name_or_document(_names, col(Supplier.document_number), text)
    conditions.append(has_every_word(col(Supplier.contact_name), text))
    conditions.append(contains(col(Supplier.contact_email), text.lower()))
    return or_(*conditions)


def list_suppliers(
    session: Session, filters: SupplierFilters, params: PageParams, request: Request
) -> Page:
    statement = select(Supplier, _active_services)
    if filters.status == SupplierStatusFilter.ACTIVE:
        statement = statement.where(col(Supplier.is_active))
    elif filters.status == SupplierStatusFilter.INACTIVE:
        statement = statement.where(~col(Supplier.is_active))
    if filters.category is not None:
        statement = statement.where(col(Supplier.categories).contains([filters.category]))
    if filters.q:
        statement = statement.where(_search(filters.q))
    statement = statement.order_by(folded(col(Supplier.trade_name)), Supplier.id)
    return map_results(paginate(session, statement, params, request), _list_item)


def get_supplier(session: Session, supplier_id: int) -> Supplier:
    supplier = session.get(
        Supplier,
        supplier_id,
        options=[joinedload(Supplier.created_by), joinedload(Supplier.deactivated_by)],
    )
    if supplier is None:
        raise NotFound()
    return supplier
