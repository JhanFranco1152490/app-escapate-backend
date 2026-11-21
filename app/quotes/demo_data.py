"""Paquete, cotizaciones y seguimientos de demostración, sobre las solicitudes, los proveedores
y los servicios de demostración. Todo inventado.

Cada cotización muestra un momento del embudo: una en borrador (armada desde el paquete, con
una alternativa superior del hotel para comparar), una
enviada con seguimientos en rojo y en amarillo, y dos aceptadas, que la carga de ventas
convierte en venta. Las fechas son días desde la carga, para que siempre sean viajes futuros
y los colores de los seguimientos salgan iguales sin importar cuándo se corra.
"""

from dataclasses import dataclass, field
from typing import Any

from app.quotes.models import QuoteStatus

_PERSON = ("CC", "1000000101")
_COMPANY = ("NIT", "9000001028")
HOTEL = ("NIT", "9000001114")
TRANSPORT = ("NIT", "9000001121")
AIRLINE = ("FOREIGN", "DEMO000113")


@dataclass(frozen=True)
class DemoItem:
    """Un servicio de la cotización o del paquete. Con `service_name`, el del catálogo de su
    proveedor; sin él, uno escrito a mano. Las fechas, en días desde hoy."""

    supplier_document: tuple[str, str] | None
    fields: dict[str, Any]
    service_name: str | None = None
    start_in: int | None = None
    end_in: int | None = None
    # Nombre del servicio de la misma cotización del que este es una alternativa.
    alternative_of: str | None = None


@dataclass(frozen=True)
class DemoFollowUp:
    due_in: int
    channel: str
    purpose: str
    # Con resultado, el seguimiento queda hecho.
    outcome: str | None = None


@dataclass(frozen=True)
class DemoQuote:
    # La solicitud de demostración de la que nace (ver DEMO_TRAVEL_REQUESTS).
    client_document: tuple[str, str]
    destination: str
    status: QuoteStatus
    items: tuple[DemoItem, ...] = ()
    # Si se arma desde un paquete de DEMO_PACKAGES, su nombre; sus servicios se copian.
    package_name: str | None = None
    # Para las de período flexible, que nacen sin fechas.
    days_from_today: dict[str, int] = field(default_factory=dict)
    conditions: dict[str, Any] = field(default_factory=dict)
    follow_ups: tuple[DemoFollowUp, ...] = ()


@dataclass(frozen=True)
class DemoPackage:
    fields: dict[str, Any]
    items: tuple[DemoItem, ...]


_FAMILY_ROOM = DemoItem(
    HOTEL,
    {
        "service_type": "lodging",
        "name": "Habitación familiar en Santa Marta",
        "details": "Desayuno incluido.",
        "quality_level": "standard",
        "quantity": 4,
        "charge_unit": "per_night",
        "currency": "COP",
        "unit_cost": "560000",
    },
    service_name="Habitación familiar",
)
_SANTA_MARTA_TRANSFER = DemoItem(
    TRANSPORT,
    {
        "service_type": "ground",
        "name": "Traslados aeropuerto – hotel – aeropuerto",
        "quantity": 2,
        "charge_unit": "per_trip",
        "currency": "COP",
        "unit_cost": "85000",
    },
)

DEMO_PACKAGES: tuple[DemoPackage, ...] = (
    DemoPackage(
        {
            "name": "Santa Marta en familia",
            "destination": "Santa Marta",
            "description": (
                "Cuatro noches con desayuno y traslados. Ideal para dos adultos y un niño."
            ),
            "nights": 4,
            "reference_travelers": 3,
            "default_markup_percent": "18.00",
        },
        (_FAMILY_ROOM, _SANTA_MARTA_TRANSFER),
    ),
)

_CONDITIONS = {
    "deposit_percent": "40.00",
    "payment_terms": "Abono del 40 % para reservar y saldo 15 días antes del viaje.",
    "policies": "Tarifas sujetas a disponibilidad hasta el pago del abono.",
}

DEMO_QUOTES: tuple[DemoQuote, ...] = (
    DemoQuote(
        _PERSON,
        "San Andrés",
        QuoteStatus.ACCEPTED,
        items=(
            DemoItem(
                AIRLINE,
                {
                    "service_type": "air",
                    "name": "Tiquetes Cúcuta – San Andrés ida y regreso",
                    "quantity": 3,
                    "charge_unit": "per_person",
                    "currency": "COP",
                    "unit_cost": "850000",
                    "supplier_commission_percent": "3.00",
                },
                start_in=35,
                end_in=41,
            ),
            DemoItem(
                HOTEL,
                {
                    "service_type": "lodging",
                    "name": "Hotel frente al mar, habitación triple",
                    "details": "Desayuno incluido.",
                    "quantity": 6,
                    "charge_unit": "per_night",
                    "currency": "COP",
                    "unit_cost": "520000",
                    "supplier_commission_percent": "10.00",
                },
                start_in=35,
                end_in=41,
            ),
            DemoItem(
                TRANSPORT,
                {
                    "service_type": "ground",
                    "name": "Traslados aeropuerto – hotel",
                    "quantity": 2,
                    "charge_unit": "per_trip",
                    "currency": "COP",
                    "unit_cost": "90000",
                },
                start_in=35,
                end_in=41,
            ),
            DemoItem(
                None,
                {
                    "service_type": "tours",
                    "name": "Tour a Johnny Cay y el acuario",
                    "quantity": 3,
                    "charge_unit": "per_person",
                    "is_optional": True,
                    "currency": "COP",
                    "unit_cost": "120000",
                },
                start_in=37,
            ),
        ),
        conditions=_CONDITIONS,
        follow_ups=(
            DemoFollowUp(
                -3,
                "whatsapp",
                "Confirmar que recibió la propuesta",
                outcome="La revisó con la familia. Acepta y paga en dos abonos.",
            ),
        ),
    ),
    DemoQuote(
        _COMPANY,
        "Medellín",
        QuoteStatus.ACCEPTED,
        items=(
            DemoItem(
                AIRLINE,
                {
                    "service_type": "air",
                    "name": "Tiquetes Bogotá – Medellín ida y regreso",
                    "quantity": 6,
                    "charge_unit": "per_person",
                    "currency": "COP",
                    "unit_cost": "420000",
                },
                start_in=20,
                end_in=23,
            ),
            DemoItem(
                HOTEL,
                {
                    "service_type": "lodging",
                    "name": "Hotel ejecutivo, tres habitaciones dobles",
                    "quantity": 9,
                    "charge_unit": "per_night",
                    "currency": "COP",
                    "unit_cost": "310000",
                    "markup_percent": "12.00",
                },
                start_in=20,
                end_in=23,
            ),
        ),
        conditions={"payment_terms": "Pago total contra factura."},
    ),
    DemoQuote(
        _COMPANY,
        "Eje Cafetero",
        QuoteStatus.SENT,
        items=(
            DemoItem(
                None,
                {
                    "service_type": "lodging",
                    "name": "Finca cafetera para 12 personas",
                    "details": "Seis habitaciones dobles con desayuno.",
                    "quantity": 3,
                    "charge_unit": "per_night",
                    "currency": "COP",
                    "unit_cost": "1800000",
                },
            ),
            DemoItem(
                None,
                {
                    "service_type": "tours",
                    "name": "Recorrido por el Valle de Cocora",
                    "quantity": 12,
                    "charge_unit": "per_person",
                    "currency": "COP",
                    "unit_cost": "95000",
                },
            ),
        ),
        days_from_today={"departure_date": 50, "return_date": 53},
        conditions=_CONDITIONS,
        follow_ups=(
            DemoFollowUp(-2, "call", "Resolver las dudas sobre el itinerario"),
            DemoFollowUp(1, "email", "Enviar fotos de la finca"),
        ),
    ),
    DemoQuote(
        _PERSON,
        "Cartagena y Santa Marta",
        QuoteStatus.DRAFT,
        package_name="Santa Marta en familia",
        items=(
            DemoItem(
                None,
                {
                    "service_type": "lodging",
                    "name": "Suite frente al mar en Santa Marta",
                    "details": "Desayuno y cena incluidos.",
                    "quality_level": "superior",
                    "quantity": 4,
                    "charge_unit": "per_night",
                    "currency": "COP",
                    "unit_cost": "890000",
                },
                alternative_of="Habitación familiar en Santa Marta",
            ),
        ),
        days_from_today={"departure_date": 65, "return_date": 69},
        follow_ups=(DemoFollowUp(5, "call", "Presentar la propuesta del paquete"),),
    ),
)
