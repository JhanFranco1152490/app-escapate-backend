"""Lecturas de servicios turísticos: los de un proveedor y la ficha de uno."""

from datetime import date

from fastapi import Request
from sqlalchemy import ScalarSelect, func, or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.common.dates import today
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, map_results, paginate
from app.common.search import folded
from app.suppliers.models import Supplier
from app.suppliers.tourist_service_models import ServiceRate, TouristService
from app.suppliers.tourist_service_schemas import TouristServiceDetail, TouristServiceListItem


def current_rate_count(day: date) -> ScalarSelect:
    """Cuántas tarifas del servicio valen ese día: ya empezaron y no han terminado."""
    return (
        select(func.count())
        .select_from(ServiceRate)
        .where(
            ServiceRate.tourist_service_id == TouristService.id,
            col(ServiceRate.valid_from) <= day,
            or_(col(ServiceRate.valid_until).is_(None), col(ServiceRate.valid_until) >= day),
        )
        .correlate(TouristService)
        .scalar_subquery()
    )


def list_supplier_services(
    session: Session, supplier_id: int, params: PageParams, request: Request
) -> Page:
    if session.get(Supplier, supplier_id) is None:
        raise NotFound()
    statement = (
        select(TouristService, current_rate_count(today()))
        .where(TouristService.supplier_id == supplier_id)
        .order_by(
            col(TouristService.is_active).desc(),
            folded(col(TouristService.name)),
            TouristService.id,
        )
    )
    page = paginate(session, statement, params, request)
    return map_results(page, lambda row: TouristServiceListItem.from_service(*row))


def get_tourist_service(session: Session, service_id: int) -> TouristServiceDetail:
    statement = (
        select(TouristService, current_rate_count(today()))
        .where(TouristService.id == service_id)
        .options(
            joinedload(TouristService.supplier),
            joinedload(TouristService.created_by),
            joinedload(TouristService.deactivated_by),
        )
    )
    row = session.exec(statement).first()
    if row is None:
        raise NotFound()
    return TouristServiceDetail.from_service(*row)
