"""El motor de liquidación: costo en pesos, precio de venta y totales de una cotización.

Regla acordada con la agencia (pendiente de validar con ella): el precio de venta de un
servicio es su costo en pesos más su % de ganancia, `costo x (1 + % / 100)`, salvo que el
asesor escriba el precio a mano. Los servicios opcionales no suman al total: se ofrecen
aparte, con su precio. La comisión del proveedor no entra al precio.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.common.money import apply_percentage, round_to_peso
from app.suppliers.service_types import Currency


def cost_in_pesos(
    unit_cost: Decimal, quantity: int, currency: str, exchange_rate: Decimal | None
) -> int | None:
    """El costo total del servicio en pesos, o `None` si está en dólares y la cotización
    todavía no tiene tasa de cambio."""
    total = unit_cost * quantity
    if currency == Currency.COP:
        return round_to_peso(total)
    if exchange_rate is None:
        return None
    return round_to_peso(total * exchange_rate)


def sale_price(cost: int | None, markup_percent: Decimal, override: int | None) -> int | None:
    if override is not None:
        return override
    if cost is None:
        return None
    return cost + apply_percentage(cost, markup_percent)


@dataclass(frozen=True)
class LineAmounts:
    cost: int | None
    sale: int | None
    is_optional: bool
    # Las alternativas tampoco suman: son otra opción para un servicio que ya está.
    is_alternative: bool = False


@dataclass(frozen=True)
class Totals:
    cost: int
    sale: int
    profit: int
    # La ganancia sobre el precio de venta, con dos decimales; `None` si el precio es cero.
    margin_percent: Decimal | None
    optional_sale: int
    per_person: int | None
    deposit: int | None
    # Algún servicio en dólares sin tasa: los totales no lo incluyen todavía.
    missing_exchange_rate: bool


def totals(lines: list[LineAmounts], travelers: int, deposit_percent: Decimal | None) -> Totals:
    base = [line for line in lines if not (line.is_optional or line.is_alternative)]
    cost = sum(line.cost or 0 for line in base)
    sale = sum(line.sale or 0 for line in base)
    profit = sale - cost
    margin = (Decimal(profit) * 100 / Decimal(sale)).quantize(Decimal("0.01")) if sale else None
    return Totals(
        cost=cost,
        sale=sale,
        profit=profit,
        margin_percent=margin,
        optional_sale=sum(
            line.sale or 0 for line in lines if line.is_optional and not line.is_alternative
        ),
        per_person=round_to_peso(Decimal(sale) / travelers) if travelers else None,
        deposit=apply_percentage(sale, deposit_percent) if deposit_percent else None,
        missing_exchange_rate=any(line.sale is None for line in lines),
    )
