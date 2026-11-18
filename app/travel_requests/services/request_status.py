"""El estado de una solicitud abierta según lo que tiene, en un solo lugar.

Lo llaman los servicios que crean lo que hace avanzar una solicitud (un borrador de
alternativas la pasa a "en cotización"; una cotización, a "cotizada") y reabrir una
solicitud cerrada. Cada uno lo llama dentro de su propia transacción: aquí no se hace
`commit()`. Una solicitud cerrada no se toca: solo reabrirla la vuelve a abrir.
"""

from sqlmodel import Session

from app.travel_requests.models import TravelRequest, TravelRequestStatus


def refresh_status(session: Session, request: TravelRequest) -> None:
    if request.status == TravelRequestStatus.CLOSED:
        return
    # Todavía no existen borradores ni cotizaciones: una solicitud abierta siempre es nueva.
    # Cuando existan, aquí se consulta si tiene una cotización (cotizada) o un borrador (en
    # cotización), en ese orden.
    request.status = TravelRequestStatus.NEW
