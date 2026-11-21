"""La oferta turística disponible: servicios activos con sus tarifas vigentes, para elegir
qué cotizar."""

from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlmodel import Session, col, select

from app.common.dates import today
from app.common.pagination import Page, PageParams, map_results, paginate
from app.common.search import has_every_word
from app.quotes.schemas import OfferFilters, OfferRate, OfferService
from app.suppliers.models import Supplier
from app.suppliers.tourist_service_models import ServiceRate, TouristService


def list_offer(
    session: Session, filters: OfferFilters, params: PageParams, request: Request
) -> Page:
    statement = (
        select(TouristService)
        .join(Supplier, Supplier.id == TouristService.supplier_id)
        .where(col(TouristService.is_active), col(Supplier.is_active))
    )
    if filters.service_type is not None:
        statement = statement.where(col(TouristService.service_type) == filters.service_type)
    if filters.q:
        statement = statement.where(
            or_(
                has_every_word(col(TouristService.name), filters.q),
                has_every_word(col(TouristService.destination), filters.q),
                has_every_word(col(Supplier.trade_name), filters.q),
            )
        )
    statement = statement.options(joinedload(TouristService.supplier)).order_by(
        col(TouristService.destination), col(TouristService.name), col(TouristService.id)
    )
    page = paginate(session, statement, params, request)

    ids = [service.id for service in page.results]
    day = today()
    rates = session.exec(
        select(ServiceRate)
        .where(
            col(ServiceRate.tourist_service_id).in_(ids),
            col(ServiceRate.valid_from) <= day,
            or_(col(ServiceRate.valid_until).is_(None), col(ServiceRate.valid_until) >= day),
        )
        .order_by(col(ServiceRate.amount))
    ).all()
    by_service: dict[int, list[ServiceRate]] = {}
    for rate in rates:
        by_service.setdefault(rate.tourist_service_id, []).append(rate)

    return map_results(
        page,
        lambda service: OfferService(
            id=service.id,
            service_type=service.service_type,
            name=service.name,
            destination=service.destination,
            description=service.description,
            supplier=service.supplier,
            rates=[OfferRate.model_validate(rate) for rate in by_service.get(service.id, [])],
        ),
    )
