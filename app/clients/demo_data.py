"""Clientes y viajeros de demostración, todos inventados: correos @example.com y documentos y
celulares que no pertenecen a nadie. Cada uno trae documento para que cargarlos de nuevo los
reconozca en vez de duplicarlos."""

from dataclasses import dataclass
from datetime import date
from typing import Any

DEMO_CLIENTS: tuple[dict[str, Any], ...] = (
    {
        "client_type": "person",
        "first_name": "Cliente",
        "last_name": "Demostración",
        "document_type": "CC",
        "document_number": "1000000101",
        "birth_date": date(1990, 5, 15),
        "phone": "3100000101",
        "email": "cliente.demo@example.com",
        "city": "Cúcuta",
        "contact_source": "whatsapp",
    },
    {
        "client_type": "company",
        "business_name": "Agencia Demostración SAS",
        "document_type": "NIT",
        "document_number": "9000001028",
        "phone": "3100000102",
        "email": "empresa.demo@example.com",
        "city": "Bogotá",
        "contact_source": "referral",
    },
)

# Documento de la persona de DEMO_CLIENTS que figura como cliente de referencia de los viajeros.
DEMO_REFERENCE_DOCUMENT = ("CC", "1000000101")


@dataclass(frozen=True)
class DemoTraveler:
    fields: dict[str, Any]
    has_reference_client: bool = False


DEMO_TRAVELERS: tuple[DemoTraveler, ...] = (
    DemoTraveler(
        {
            "first_name": "Cliente",
            "last_name": "Demostración",
            "document_type": "CC",
            "document_number": "1000000101",
            "birth_date": date(1990, 5, 15),
            "nationality": "CO",
            "is_the_client": True,
        },
        has_reference_client=True,
    ),
    DemoTraveler(
        {
            "first_name": "Viajero",
            "last_name": "Menor Demostración",
            "document_type": "TI",
            "document_number": "1000000202",
            "birth_date": date(2017, 3, 10),
            "nationality": "CO",
        },
        has_reference_client=True,
    ),
    DemoTraveler(
        {
            "first_name": "Viajero",
            "last_name": "Extranjero Demostración",
            "document_type": "PA",
            "document_number": "DEMO000303",
            "birth_date": date(1985, 11, 2),
            "nationality": "US",
        }
    ),
)
