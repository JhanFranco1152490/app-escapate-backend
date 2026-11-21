"""Los servicios de una cotización: agregar, editar y quitar.

Solo cambian mientras la cotización está en borrador. Cada operación lee la cotización con
`FOR SHARE`: un envío simultáneo espera o se ve, así nunca queda un servicio agregado a una
cotización ya enviada. Cambiar un servicio no edita la cotización (ni su `version`), para que
quien tiene sus datos generales abiertos no reciba un `stale_version` por eso.
"""

from sqlmodel import Session, select

from app.common.errors import InvalidFields, NotFound, StaleVersion
from app.quotes.errors import (
    BAD_ALTERNATIVE,
    CHARGE_UNIT_MISMATCH,
    INACTIVE_SERVICE,
    SERVICE_TYPE_MISMATCH,
    SUPPLIER_OF_THE_SERVICE,
    UNKNOWN_SERVICE,
    UNKNOWN_SUPPLIER,
)
from app.quotes.models import Quote, QuoteItem
from app.quotes.schemas import QuoteItemCreate, QuoteItemInput, QuoteItemUpdate
from app.quotes.services.quote_management import ensure_draft
from app.suppliers.models import Supplier
from app.suppliers.service_types import CHARGE_UNITS
from app.suppliers.tourist_service_models import TouristService


def _locked_draft(session: Session, quote_id: int) -> Quote:
    quote = session.exec(
        select(Quote).where(Quote.id == quote_id).with_for_update(read=True)
    ).first()
    if quote is None:
        raise NotFound()
    ensure_draft(quote)
    return quote


def check_references(
    session: Session,
    quote_id: int,
    data: QuoteItemInput,
    current: QuoteItem | None = None,
) -> int | None:
    """Revisa lo que el esquema no puede revisar sin la base, con todos los errores juntos.
    Devuelve el proveedor del servicio: el del catálogo, si se eligió uno."""
    fields: dict[str, list[str]] = {}
    supplier_id = data.supplier_id
    if data.tourist_service_id is not None:
        service = session.get(TouristService, data.tourist_service_id)
        if service is None:
            fields["tourist_service_id"] = [UNKNOWN_SERVICE]
        else:
            # Un servicio que ya estaba en la cotización se puede seguir editando aunque lo
            # hayan desactivado después; uno nuevo tiene que estar activo.
            kept = current is not None and current.tourist_service_id == service.id
            if not service.is_active and not kept:
                fields["tourist_service_id"] = [INACTIVE_SERVICE]
            if service.service_type != data.service_type:
                fields["service_type"] = [SERVICE_TYPE_MISMATCH]
            if supplier_id is not None and supplier_id != service.supplier_id:
                fields["supplier_id"] = [SUPPLIER_OF_THE_SERVICE]
            supplier_id = service.supplier_id
    elif supplier_id is not None and session.get(Supplier, supplier_id) is None:
        fields["supplier_id"] = [UNKNOWN_SUPPLIER]

    if data.alternative_of_id is not None:
        base = session.get(QuoteItem, data.alternative_of_id)
        # Un solo nivel: la alternativa es de un servicio incluido, no de otra alternativa.
        valid = (
            base is not None
            and base.quote_id == quote_id
            and base.alternative_of_id is None
            and (current is None or base.id != current.id)
        )
        if not valid:
            fields["alternative_of_id"] = [BAD_ALTERNATIVE]
    if data.charge_unit is not None and data.charge_unit not in CHARGE_UNITS[data.service_type]:
        fields["charge_unit"] = [CHARGE_UNIT_MISMATCH]
    if fields:
        raise InvalidFields(fields=fields)
    return supplier_id


def _values(data: QuoteItemInput, quote: Quote, supplier_id: int | None) -> dict:
    values = data.model_dump(exclude={"expected_version"})
    values["supplier_id"] = supplier_id
    if values["markup_percent"] is None:
        values["markup_percent"] = quote.default_markup_percent
    return values


def _item(session: Session, quote_id: int, item_id: int) -> QuoteItem:
    item = session.get(QuoteItem, item_id)
    if item is None or item.quote_id != quote_id:
        raise NotFound()
    return item


def add_item(session: Session, quote_id: int, data: QuoteItemCreate) -> QuoteItem:
    quote = _locked_draft(session, quote_id)
    supplier_id = check_references(session, quote.id, data)
    item = QuoteItem(quote_id=quote.id, **_values(data, quote, supplier_id))
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_item(session: Session, quote_id: int, item_id: int, data: QuoteItemUpdate) -> QuoteItem:
    quote = _locked_draft(session, quote_id)
    item = _item(session, quote_id, item_id)
    if data.expected_version != item.version:
        raise StaleVersion()
    supplier_id = check_references(session, quote.id, data, current=item)
    for name, value in _values(data, quote, supplier_id).items():
        setattr(item, name, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def remove_item(session: Session, quote_id: int, item_id: int) -> None:
    _locked_draft(session, quote_id)
    session.delete(_item(session, quote_id, item_id))
    session.commit()
