"""Datos inventados de servicios turísticos que comparten varias pruebas."""

from app.suppliers.service_types import ServiceType

# Los atributos mínimos y completos de cada tipo, ya válidos.
MINIMAL = {
    ServiceType.LODGING: {"lodging_kind": "hotel", "max_capacity": 4},
    ServiceType.AIR: {"origin": "Bogotá (BOG)", "trip_type": "round_trip"},
    ServiceType.GROUND: {"modality": "private"},
    ServiceType.TOURS: {"duration_value": 4, "duration_unit": "hours"},
    ServiceType.CRUISE: {"ship_name": "Barco de prueba", "departure_port": "Miami", "nights": 7},
    ServiceType.FOOD: {"meals": ["dinner"]},
    ServiceType.WHOLESALER: {"nights": 0},
    ServiceType.OTHER: {},
}

COMPLETE = {
    ServiceType.LODGING: {
        "lodging_kind": "resort",
        "stars": 5,
        "meal_plan": "all_inclusive",
        "max_capacity": 4,
        "check_in_time": "15:00",
        "check_out_time": "12:00",
        "includes": ["wifi", "airport_transfers"],
    },
    ServiceType.AIR: {
        "origin": "Bogotá (BOG)",
        "trip_type": "one_way",
        "cabin_class": "business",
        "stops": 1,
        "carry_on_included": True,
        "checked_bags": 2,
    },
    ServiceType.GROUND: {
        "modality": "shared",
        "vehicle_kind": "van",
        "origin": "Aeropuerto de prueba",
        "max_capacity": 12,
    },
    ServiceType.TOURS: {
        "duration_value": 2,
        "duration_unit": "days",
        "modality": "private",
        "meeting_point": "Lobby del hotel",
        "includes": ["guide", "transport"],
    },
    ServiceType.CRUISE: {
        "ship_name": "Barco de prueba",
        "departure_port": "Miami",
        "nights": 7,
        "cabin_kind": "balcony",
        "itinerary": "Miami, Cozumel, Roatán",
        "includes": ["meals", "port_fees"],
    },
    ServiceType.FOOD: {
        "meals": ["dinner", "lunch"],
        "service_style": "buffet",
        "cuisine": "Caribeña",
    },
    ServiceType.WHOLESALER: {
        "nights": 5,
        "departure_city": "Bogotá",
        "includes": ["flights", "lodging", "transfers"],
    },
    ServiceType.OTHER: {},
}
