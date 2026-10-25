"""Alta y edición de clientes.

Cada operación hace un solo `commit()`. El documento es opcional, pero si se registra no
puede tenerlo otro cliente con el mismo tipo. La autorización de datos se registra al crear
y la edición no la cambia.
"""

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.clients.errors import ClientTypeChanged, DuplicateClient
from app.clients.models import Client
from app.clients.schemas import ClientCreate, ClientInput, ClientUpdate
from app.clients.services.client_queries import get_client
from app.common.database import database_conflicts
from app.common.errors import StaleVersion

_CONFLICTS = {"uq_client_document": DuplicateClient}


def _ensure_document_is_free(
    session: Session, data: ClientInput, exclude_id: int | None = None
) -> None:
    if data.document_number is None:
        return
    statement = select(Client.id).where(
        Client.document_type == data.document_type,
        Client.document_number == data.document_number,
    )
    if exclude_id is not None:
        statement = statement.where(Client.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise DuplicateClient()


def create_client(session: Session, actor: UserAccount, data: ClientCreate) -> Client:
    _ensure_document_is_free(session, data)
    client = Client(
        **data.model_dump(exclude={"data_consent"}),
        created_by_id=actor.id,
        data_consent_by_id=actor.id,
    )
    with database_conflicts(session, _CONFLICTS):
        session.add(client)
        session.commit()
    return get_client(session, client.id)


def update_client(session: Session, client_id: int, data: ClientUpdate) -> Client:
    client = get_client(session, client_id)
    if data.client_type != client.client_type:
        raise ClientTypeChanged()
    # La revisión da el error claro; si otra petición guarda entre esta lectura y el commit,
    # el bloqueo optimista del modelo responde lo mismo.
    if data.expected_version != client.version:
        raise StaleVersion()
    _ensure_document_is_free(session, data, exclude_id=client.id)

    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(client, name, value)
    with database_conflicts(session, _CONFLICTS):
        session.commit()
    return get_client(session, client.id)
