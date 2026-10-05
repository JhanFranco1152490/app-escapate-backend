from datetime import date, datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def today() -> date:
    """Fecha de hoy en Bogotá; el servidor suele correr en UTC."""
    return datetime.now(BOGOTA).date()
