"""Proveedores de demostración, todos inventados: correos @example.com y documentos y celulares
que no pertenecen a nadie. Cada uno trae documento para que cargarlos de nuevo los reconozca en
vez de duplicarlos."""

from datetime import date
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
)
