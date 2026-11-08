"""Listas fijas de los servicios turísticos y sus tarifas. Modelos, esquemas y servicios las
leen de aquí para que todos acepten exactamente lo mismo. El orden de cada enum es el de las
pantallas."""

from enum import StrEnum

from app.suppliers.models import SupplierCategory

# El tipo de un servicio es una de las clasificaciones de su proveedor: la misma lista, para
# que "qué vende" y "qué servicios tiene" no puedan decir cosas distintas.
ServiceType = SupplierCategory

SERVICE_TYPE_LABELS: dict[ServiceType, str] = {
    ServiceType.LODGING: "Alojamiento",
    ServiceType.AIR: "Transporte aéreo",
    ServiceType.GROUND: "Transporte terrestre",
    ServiceType.TOURS: "Tours y actividades",
    ServiceType.CRUISE: "Cruceros",
    ServiceType.FOOD: "Alimentación",
    ServiceType.WHOLESALER: "Mayorista",
    ServiceType.OTHER: "Otro",
}


class Currency(StrEnum):
    """La moneda en que el proveedor da la tarifa. No se convierte al registrar: la tasa de
    cambio varía cada día."""

    COP = "COP"
    USD = "USD"


class ChargeUnit(StrEnum):
    """Sobre qué se cobra el valor de una tarifa: dice si al usarla hay que multiplicar por
    noches, por personas o por nada."""

    PER_NIGHT = "per_night"
    PER_PERSON_PER_NIGHT = "per_person_per_night"
    PER_PERSON = "per_person"
    PER_TRIP = "per_trip"
    PER_DAY = "per_day"
    PER_GROUP = "per_group"
    PER_CABIN = "per_cabin"
    PER_PACKAGE = "per_package"
    PER_SERVICE = "per_service"


# La primera de cada tipo es la que el formulario trae elegida.
CHARGE_UNITS: dict[ServiceType, tuple[ChargeUnit, ...]] = {
    ServiceType.LODGING: (ChargeUnit.PER_NIGHT, ChargeUnit.PER_PERSON_PER_NIGHT),
    ServiceType.AIR: (ChargeUnit.PER_PERSON,),
    ServiceType.GROUND: (ChargeUnit.PER_TRIP, ChargeUnit.PER_PERSON, ChargeUnit.PER_DAY),
    ServiceType.TOURS: (ChargeUnit.PER_PERSON, ChargeUnit.PER_GROUP),
    ServiceType.CRUISE: (ChargeUnit.PER_PERSON, ChargeUnit.PER_CABIN),
    ServiceType.FOOD: (ChargeUnit.PER_PERSON,),
    ServiceType.WHOLESALER: (ChargeUnit.PER_PERSON, ChargeUnit.PER_PACKAGE),
    ServiceType.OTHER: (ChargeUnit.PER_SERVICE, ChargeUnit.PER_PERSON, ChargeUnit.PER_DAY),
}


class LodgingKind(StrEnum):
    HOTEL = "hotel"
    RESORT = "resort"
    HOSTEL = "hostel"
    APARTMENT = "apartment"
    CABIN = "cabin"
    OTHER = "other"


class MealPlan(StrEnum):
    ROOM_ONLY = "room_only"
    BREAKFAST = "breakfast"
    HALF_BOARD = "half_board"
    FULL_BOARD = "full_board"
    ALL_INCLUSIVE = "all_inclusive"


class LodgingInclude(StrEnum):
    # Las comidas no van aquí: las dice el régimen.
    AIRPORT_TRANSFERS = "airport_transfers"
    RECREATIONAL_ACTIVITIES = "recreational_activities"
    WIFI = "wifi"
    PARKING = "parking"


class TripType(StrEnum):
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"


class CabinClass(StrEnum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class Modality(StrEnum):
    """Privado o compartido; la usan traslados y tours."""

    PRIVATE = "private"
    SHARED = "shared"


class VehicleKind(StrEnum):
    CAR = "car"
    VAN = "van"
    MINIBUS = "minibus"
    BUS = "bus"
    OTHER = "other"


class DurationUnit(StrEnum):
    HOURS = "hours"
    DAYS = "days"


class ToursInclude(StrEnum):
    TRANSPORT = "transport"
    GUIDE = "guide"
    ENTRANCE_FEES = "entrance_fees"
    MEALS = "meals"
    INSURANCE = "insurance"


class CabinKind(StrEnum):
    INSIDE = "inside"
    OCEAN_VIEW = "ocean_view"
    BALCONY = "balcony"
    SUITE = "suite"


class CruiseInclude(StrEnum):
    MEALS = "meals"
    DRINKS_PACKAGE = "drinks_package"
    PORT_FEES = "port_fees"
    GRATUITIES = "gratuities"
    EXCURSIONS = "excursions"


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class ServiceStyle(StrEnum):
    BUFFET = "buffet"
    SET_MENU = "set_menu"
    A_LA_CARTE = "a_la_carte"


class WholesalerInclude(StrEnum):
    FLIGHTS = "flights"
    LODGING = "lodging"
    TRANSFERS = "transfers"
    TOURS = "tours"
    MEALS = "meals"
    TRAVEL_INSURANCE = "travel_insurance"
