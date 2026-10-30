"""Alta y edición de viajeros.

Cada operación hace un solo `commit()`. El viajero es un registro propio: su cliente de
referencia es opcional, y "es el mismo cliente" no copia ni sincroniza datos con la ficha del
cliente. Un cliente tiene a lo sumo un viajero marcado así, y solo si es una persona.
"""

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.clients.errors import ClientAlreadyTraveler, DuplicateTraveler, InvalidReferenceClient
from app.clients.models import Client, ClientType, Traveler
from app.clients.schemas import TravelerCreate, TravelerInput, TravelerUpdate
from app.clients.services.traveler_queries import get_traveler
from app.common.database import database_conflicts
from app.common.errors import InvalidFields, StaleVersion

_CONFLICTS = {
    "uq_traveler_document": DuplicateTraveler,
    "uq_traveler_is_the_client": ClientAlreadyTraveler,
}


def _ensure_document_is_free(
    session: Session, data: TravelerInput, exclude_id: int | None = None
) -> list[InvalidFields]:
    statement = select(Traveler.id).where(
        Traveler.document_type == data.document_type,
        Traveler.document_number == data.document_number,
    )
    if exclude_id is not None:
        statement = statement.where(Traveler.id != exclude_id)
    return [DuplicateTraveler()] if session.exec(statement).first() is not None else []


def _check_reference(
    session: Session, data: TravelerInput, exclude_id: int | None = None
) -> list[InvalidFields]:
    if data.reference_client_id is None:
        return []
    client = session.get(Client, data.reference_client_id)
    if client is None:
        return [InvalidReferenceClient.missing()]
    if not data.is_the_client:
        return []
    if client.client_type == ClientType.COMPANY:
        return [InvalidReferenceClient.company()]
    statement = select(Traveler.id).where(
        Traveler.reference_client_id == client.id, Traveler.is_the_client
    )
    if exclude_id is not None:
        statement = statement.where(Traveler.id != exclude_id)
    return [ClientAlreadyTraveler()] if session.exec(statement).first() is not None else []


def _validate(session: Session, data: TravelerInput, exclude_id: int | None = None) -> None:
    """Revisa todo antes de responder: el formulario muestra todos los problemas a la vez."""
    problems = _ensure_document_is_free(session, data, exclude_id) + _check_reference(
        session, data, exclude_id
    )
    if len(problems) == 1:
        raise problems[0]
    if problems:
        raise InvalidFields(
            fields={
                field: messages for error in problems for field, messages in error.fields.items()
            }
        )


def create_traveler(session: Session, actor: UserAccount, data: TravelerCreate) -> Traveler:
    _validate(session, data)
    traveler = Traveler(
        **data.model_dump(exclude={"data_consent"}),
        created_by_id=actor.id,
        data_consent_by_id=actor.id,
    )
    with database_conflicts(session, _CONFLICTS):
        session.add(traveler)
        session.commit()
    return get_traveler(session, traveler.id)


def update_traveler(session: Session, traveler_id: int, data: TravelerUpdate) -> Traveler:
    traveler = get_traveler(session, traveler_id)
    if data.expected_version != traveler.version:
        raise StaleVersion()
    _validate(session, data, exclude_id=traveler.id)

    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(traveler, name, value)
    with database_conflicts(session, _CONFLICTS):
        session.commit()
    return get_traveler(session, traveler.id)
