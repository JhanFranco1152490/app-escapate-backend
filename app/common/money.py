from decimal import ROUND_HALF_UP, Decimal

_PESO = Decimal("1")


def round_to_peso(value: Decimal) -> int:
    """Redondea al peso; es la única regla de redondeo de dinero del sistema."""
    if not isinstance(value, Decimal):
        raise TypeError("round_to_peso recibe Decimal, no float")
    return int(value.quantize(_PESO, rounding=ROUND_HALF_UP))


def apply_percentage(amount: int, percentage: Decimal) -> int:
    return round_to_peso(Decimal(amount) * percentage / Decimal(100))
