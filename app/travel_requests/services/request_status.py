"""El estado de una solicitud abierta según lo que tiene, en un solo lugar.

Lo llaman los servicios que crean lo que hace avanzar una solicitud (una cotización la pasa a
"cotizada") y reabrir una solicitud cerrada. Cada uno lo llama dentro de su propia
transacción: aquí no se hace `commit()`. Una solicitud cerrada no se toca: solo reabrirla la
vuelve a abrir.
"""

from sqlalchemy import column, exists, table
from sqlmodel import Session, select

from app.travel_requests.models import TravelRequest, TravelRequestStatus

# Solo la columna que hace falta, sin importar el modelo: las cotizaciones dependen de las
# solicitudes, y importar su modelo aquí cerraría un ciclo entre los dos dominios.
_quote = table("quote", column("travel_request_id"))


def refresh_status(session: Session, request: TravelRequest) -> None:
    if request.status == TravelRequestStatus.CLOSED:
        return
    has_quote = session.exec(
        select(exists().where(_quote.c.travel_request_id == request.id))
    ).one()
    request.status = TravelRequestStatus.QUOTED if has_quote else TravelRequestStatus.NEW
