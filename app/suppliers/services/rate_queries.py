"""Lecturas de las tarifas de un servicio."""

from fastapi import Request
from sqlalchemy import case
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.common.dates import today
from app.common.errors import NotFound
from app.common.pagination import Page, PageParams, paginate
from app.common.search import folded
from app.suppliers.tourist_service_models import ServiceRate, TouristService


def list_service_rates(
    session: Session, service_id: int, params: PageParams, request: Request
) -> Page:
    if session.get(TouristService, service_id) is None:
        raise NotFound()
    day = today()
    # Primero las que valen hoy, luego las que vienen y al final las vencidas: es el orden en
    # que se van a usar.
    by_validity = case(
        (col(ServiceRate.valid_from) > day, 1),
        (col(ServiceRate.valid_until) < day, 2),
        else_=0,
    )
    statement = (
        select(ServiceRate)
        .where(ServiceRate.tourist_service_id == service_id)
        .options(joinedload(ServiceRate.created_by))
        .order_by(
            by_validity, ServiceRate.valid_from, folded(col(ServiceRate.name)), ServiceRate.id
        )
    )
    return paginate(session, statement, params, request)


def get_service_rate(session: Session, service_id: int, rate_id: int) -> ServiceRate:
    rate = session.get(ServiceRate, rate_id, options=[joinedload(ServiceRate.created_by)])
    # Una tarifa de otro servicio es como si no existiera: la ruta dice de cuál es.
    if rate is None or rate.tourist_service_id != service_id:
        raise NotFound()
    return rate
