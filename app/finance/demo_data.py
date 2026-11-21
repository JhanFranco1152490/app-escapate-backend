"""Costos reales y gastos de operación de demostración. Todo inventado.

Los costos reales van sobre las ventas de demostración: en una el tiquete salió más caro que lo
cotizado y el hotel todavía se le debe al proveedor; la otra quedó pagada como se cotizó. Los
gastos caen en los últimos días y hace un mes, para que el flujo de caja muestre más de un mes.
"""

from dataclasses import dataclass

_HOTEL = ("NIT", "9000001114")
_AIRLINE = ("FOREIGN", "DEMO000113")


@dataclass(frozen=True)
class DemoCost:
    description: str
    supplier_document: tuple[str, str] | None
    amount: int
    # Días desde hoy en que se le pagó al proveedor; sin valor, se le debe.
    paid_in: int | None


@dataclass(frozen=True)
class DemoSaleCosts:
    # La venta de demostración (ver DEMO_SALES).
    client_document: tuple[str, str]
    destination: str
    costs: tuple[DemoCost, ...]


@dataclass(frozen=True)
class DemoExpense:
    spent_in: int
    category: str
    description: str
    amount: int


DEMO_SALE_COSTS: tuple[DemoSaleCosts, ...] = (
    DemoSaleCosts(
        ("CC", "1000000101"),
        "San Andrés",
        (
            DemoCost("Tiquetes aéreos (subió la tarifa)", _AIRLINE, 2_640_000, -1),
            DemoCost("Hotel en San Andrés", _HOTEL, 3_120_000, None),
        ),
    ),
    DemoSaleCosts(
        ("NIT", "9000001028"),
        "Medellín",
        (
            DemoCost("Tiquetes aéreos", _AIRLINE, 2_520_000, -9),
            DemoCost("Hotel en Medellín", _HOTEL, 2_790_000, -9),
        ),
    ),
)

DEMO_EXPENSES: tuple[DemoExpense, ...] = (
    DemoExpense(-2, "rent", "Arriendo de la oficina (demostración)", 1_800_000),
    DemoExpense(-4, "software", "Suscripción de software (demostración)", 120_000),
    DemoExpense(-6, "marketing", "Pauta en redes sociales (demostración)", 450_000),
    DemoExpense(-32, "rent", "Arriendo de la oficina, pago anterior (demostración)", 1_800_000),
    DemoExpense(-35, "payroll", "Nómina (demostración)", 3_500_000),
)
