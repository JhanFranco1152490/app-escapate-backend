"""Solicitudes de viaje de demostración, de los clientes de demostración. Todo inventado.

Las fechas son días a partir de la carga, para que siempre sean viajes futuros. Una solicitud
se reconoce por su cliente y su destino: cargarla otro día no la duplica.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DemoTravelRequest:
    # Documento del cliente de demostración que la pide.
    client_document: tuple[str, str]
    destination: str
    # Días desde hoy de cada fecha del formulario (salida, regreso, inicio y fin del período).
    days_from_today: dict[str, int]
    fields: dict[str, Any] = field(default_factory=dict)
    # Documento de la cuenta de demostración responsable; si no se da, el autor de la carga.
    advisor_document: tuple[str, str] | None = None
    close_reason: str | None = None


_PERSON = ("CC", "1000000101")
_COMPANY = ("NIT", "9000001028")
_ADVISOR = ("CC", "1000000002")

DEMO_TRAVEL_REQUESTS: tuple[DemoTravelRequest, ...] = (
    DemoTravelRequest(
        client_document=_PERSON,
        destination="San Andrés",
        days_from_today={"departure_date": 35, "return_date": 41},
        fields={
            "date_mode": "exact",
            "origin": "Cúcuta",
            "adults": 2,
            "minors": 1,
            "budget_min": 6_000_000,
            "budget_max": 8_000_000,
            "trip_types": ["family"],
            "accommodation_category": "four_star",
            "notes": "Prefieren habitación conectada.\nEvitar vuelos con escala nocturna.",
        },
        advisor_document=_ADVISOR,
    ),
    DemoTravelRequest(
        client_document=_PERSON,
        destination="Cartagena y Santa Marta",
        days_from_today={"window_start": 60, "window_end": 90},
        fields={
            "date_mode": "flexible",
            "approx_nights": 5,
            "adults": 2,
            "minors": 0,
            "trip_types": ["leisure", "honeymoon"],
        },
        advisor_document=_ADVISOR,
    ),
    DemoTravelRequest(
        client_document=_PERSON,
        destination="Cancún",
        days_from_today={"departure_date": 50},
        fields={"date_mode": "exact", "adults": 4, "minors": 0, "budget_max": 20_000_000},
        advisor_document=_ADVISOR,
        close_reason="no_response",
    ),
    DemoTravelRequest(
        client_document=_COMPANY,
        destination="Medellín",
        days_from_today={"departure_date": 20, "return_date": 23},
        fields={
            "date_mode": "exact",
            "origin": "Bogotá",
            "adults": 6,
            "minors": 0,
            "trip_types": ["corporate", "group"],
            "accommodation_category": "three_star",
        },
    ),
    DemoTravelRequest(
        client_document=_COMPANY,
        destination="Eje Cafetero",
        days_from_today={"window_start": 45, "window_end": 75},
        fields={"date_mode": "flexible", "adults": 12, "minors": 0, "trip_types": ["group"]},
        advisor_document=_ADVISOR,
    ),
)
