from datetime import date, datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def today() -> date:
    """Fecha de hoy en Bogotá; el servidor suele correr en UTC."""
    return datetime.now(BOGOTA).date()


def age_on(birth_date: date, day: date) -> int:
    """Años cumplidos en `day`. Quien nació un 29 de febrero los cumple el 1 de marzo en los
    años no bisiestos."""
    birthday_passed = (day.month, day.day) >= (birth_date.month, birth_date.day)
    return day.year - birth_date.year - (0 if birthday_passed else 1)
