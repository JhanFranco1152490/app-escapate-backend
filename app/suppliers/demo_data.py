"""Proveedores, servicios y tarifas de demostración, todos inventados: correos @example.com y
documentos y celulares que no pertenecen a nadie. Cada proveedor trae documento para que
cargarlos de nuevo los reconozca en vez de duplicarlos."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

DEMO_SUPPLIERS: tuple[dict[str, Any], ...] = (
    {
        "trade_name": "Hotel Demostración",
        "legal_name": "Hotel Demostración SAS",
        "document_type": "NIT",
        "document_number": "9000001114",
        "categories": ["lodging"],
        "city": "Santa Marta",
        "contact_name": "Contacto Hotel",
        "contact_role": "Ventas",
        "contact_phone": "3200000111",
        "payment_terms": "Anticipo del 50 % y saldo antes de la llegada.",
        "commission_rate": "10.00",
        "agreement_valid_until": date(2030, 12, 31),
    },
    {
        "trade_name": "Transportes y Tours Demostración",
        "document_type": "NIT",
        "document_number": "9000001121",
        "categories": ["ground", "tours"],
        "city": "Cúcuta",
        "coverage_zone": "Norte de Santander",
        "contact_name": "Contacto Transportes",
        "contact_email": "transportes.demo@example.com",
    },
    {
        "trade_name": "Aerolínea Demostración",
        "document_type": "FOREIGN",
        "document_number": "DEMO000113",
        "categories": ["air"],
        "contact_name": "Contacto Aerolínea",
        "contact_email": "aerolinea.demo@example.com",
        "contact_phone": "3200000113",
    },
    {
        "trade_name": "Naviera Demostración",
        "document_type": "FOREIGN",
        "document_number": "DEMO000114",
        "categories": ["cruise"],
        "contact_name": "Contacto Naviera",
        "contact_email": "naviera.demo@example.com",
    },
)


@dataclass(frozen=True)
class DemoRate:
    """Una tarifa con su vigencia en días desde hoy, para que la carga muestre siempre una
    vigente, una próxima y una vencida sin importar cuándo se corra."""

    name: str
    starts_in: int
    ends_in: int | None
    amount: str
    charge_unit: str
    currency: str = "COP"
    conditions: str | None = None

    def fields(self, day: date) -> dict[str, Any]:
        return {
            "name": self.name,
            "valid_from": day + timedelta(days=self.starts_in),
            "valid_until": None if self.ends_in is None else day + timedelta(days=self.ends_in),
            "currency": self.currency,
            "charge_unit": self.charge_unit,
            "amount": self.amount,
            "conditions": self.conditions,
        }


@dataclass(frozen=True)
class DemoService:
    supplier_document: tuple[str, str]
    fields: dict[str, Any]
    rates: tuple[DemoRate, ...]
    active: bool = True


_HOTEL = ("NIT", "9000001114")
_TRANSPORT = ("NIT", "9000001121")
_CRUISE_LINE = ("FOREIGN", "DEMO000114")

DEMO_TOURIST_SERVICES: tuple[DemoService, ...] = (
    DemoService(
        _HOTEL,
        {
            "service_type": "lodging",
            "name": "Habitación familiar",
            "destination": "Santa Marta",
            "conditions": "Cancelación sin costo hasta 15 días antes.",
            "attributes": {
                "lodging_kind": "hotel",
                "meal_plan": "breakfast",
                "max_capacity": 4,
                "check_in_time": "15:00",
                "check_out_time": "12:00",
                "includes": ["wifi"],
            },
        },
        (
            DemoRate(
                "Temporada alta", -10, 20, "710000", "per_night", conditions="Mínimo 3 noches."
            ),
            DemoRate("Temporada media", 21, 120, "560000", "per_night"),
            DemoRate("Temporada baja", -120, -11, "480000", "per_night"),
            DemoRate("Persona adicional", -120, None, "120000", "per_person_per_night"),
        ),
    ),
    DemoService(
        _TRANSPORT,
        {
            "service_type": "ground",
            "name": "Traslado aeropuerto – hotel",
            "destination": "Cúcuta",
            "attributes": {
                "modality": "private",
                "vehicle_kind": "van",
                "origin": "Aeropuerto de Cúcuta",
                "max_capacity": 8,
            },
        },
        (DemoRate("Tarifa general", -30, None, "90000", "per_trip"),),
        active=False,
    ),
    DemoService(
        _TRANSPORT,
        {
            "service_type": "tours",
            "name": "Recorrido por el centro histórico",
            "destination": "Cúcuta",
            "attributes": {
                "duration_value": 4,
                "duration_unit": "hours",
                "modality": "shared",
                "meeting_point": "Parque Santander",
                "includes": ["guide"],
            },
        },
        (DemoRate("Tarifa general", -30, None, "65000", "per_person"),),
    ),
    DemoService(
        _CRUISE_LINE,
        {
            "service_type": "cruise",
            "name": "Caribe occidental 7 noches",
            "destination": "Caribe",
            "attributes": {
                "ship_name": "Barco Demostración",
                "departure_port": "Miami",
                "nights": 7,
                "cabin_kind": "balcony",
                "includes": ["meals", "port_fees"],
            },
        },
        (DemoRate("Cabina con balcón", -5, 60, "1249.90", "per_person", currency="USD"),),
    ),
)
