from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import factory

from app.accounts.models import Role, UserAccount
from app.clients.models import Client, Traveler
from app.common.dates import today
from app.common.identifiers import nit_check_digit
from app.core.security.passwords import hash_password
from app.suppliers.models import Supplier
from app.suppliers.tourist_service_models import ServiceRate, TouristService
from app.travel_requests.models import TravelRequest

PASSWORD = "contrasena-de-prueba-123"
# Argon2 es lento a propósito: un solo hash para todas las cuentas de prueba.
PASSWORD_HASH = hash_password(PASSWORD)

_current = {"session": None}


def use_session(session) -> None:
    """Las fábricas escriben en la sesión de la prueba en curso (con rollback al final)."""
    _current["session"] = session


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_factory = lambda: _current["session"]  # noqa: E731
        sqlalchemy_session_persistence = "flush"


class RoleFactory(BaseFactory):
    class Meta:
        model = Role

    name = factory.Sequence(lambda n: f"Rol de prueba {n}")


class UserAccountFactory(BaseFactory):
    class Meta:
        model = UserAccount

    email = factory.Sequence(lambda n: f"persona{n}@example.com")
    first_name = "Persona"
    last_name = factory.Sequence(lambda n: f"Apellido {n}")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: str(10_000_000 + n))
    phone = factory.Sequence(lambda n: f"300{n:07d}")
    password_hash = PASSWORD_HASH
    is_active = True
    role = factory.SubFactory(RoleFactory)


class ClientFactory(BaseFactory):
    """Una persona con cédula por defecto; `company=True` da una empresa sin documento."""

    class Meta:
        model = Client

    class Params:
        company = factory.Trait(
            client_type="company",
            first_name=None,
            last_name=None,
            business_name=factory.Sequence(lambda n: f"Empresa de prueba {n} SAS"),
            document_type=None,
            document_number=None,
        )

    client_type = "person"
    first_name = "Cliente"
    last_name = factory.Sequence(lambda n: f"Apellido {n}")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: str(20_000_000 + n))
    phone = factory.Sequence(lambda n: f"+57310{n:07d}")
    contact_source = "whatsapp"
    created_by = factory.SubFactory(UserAccountFactory)
    data_consent_by = factory.SelfAttribute("created_by")


class TravelerFactory(BaseFactory):
    class Meta:
        model = Traveler

    first_name = "Viajero"
    last_name = factory.Sequence(lambda n: f"Apellido {n}")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: str(30_000_000 + n))
    birth_date = date(1990, 1, 1)
    nationality = "CO"
    created_by = factory.SubFactory(UserAccountFactory)
    data_consent_by = factory.SelfAttribute("created_by")


def _invented_nit(n: int) -> str:
    base = str(900_000_000 + n)
    return f"{base}{nit_check_digit(base)}"


class SupplierFactory(BaseFactory):
    """Un proveedor activo de alojamiento con NIT; `inactive=True` lo da desactivado."""

    class Meta:
        model = Supplier

    class Params:
        inactive = factory.Trait(
            is_active=False,
            deactivated_at=factory.LazyFunction(lambda: datetime.now(timezone.utc)),
            deactivated_by=factory.SelfAttribute("created_by"),
        )

    trade_name = factory.Sequence(lambda n: f"Proveedor de prueba {n}")
    document_type = "NIT"
    document_number = factory.Sequence(_invented_nit)
    categories = factory.LazyFunction(lambda: ["lodging"])
    contact_name = "Contacto de prueba"
    contact_phone = factory.Sequence(lambda n: f"+57320{n:07d}")
    created_by = factory.SubFactory(UserAccountFactory)


class TouristServiceFactory(BaseFactory):
    """Un alojamiento activo con los atributos mínimos; `inactive=True` lo da desactivado."""

    class Meta:
        model = TouristService

    class Params:
        inactive = factory.Trait(
            is_active=False,
            deactivated_at=factory.LazyFunction(lambda: datetime.now(timezone.utc)),
            deactivated_by=factory.SelfAttribute("created_by"),
        )

    supplier = factory.SubFactory(SupplierFactory)
    service_type = "lodging"
    name = factory.Sequence(lambda n: f"Servicio de prueba {n}")
    destination = "Cartagena"
    attributes = factory.LazyFunction(
        lambda: {"lodging_kind": "hotel", "max_capacity": 2, "includes": []}
    )
    created_by = factory.SelfAttribute("supplier.created_by")


class ServiceRateFactory(BaseFactory):
    """Una tarifa en pesos, vigente desde hoy y sin fecha final."""

    class Meta:
        model = ServiceRate

    tourist_service = factory.SubFactory(TouristServiceFactory)
    name = factory.Sequence(lambda n: f"Tarifa de prueba {n}")
    valid_from = factory.LazyFunction(today)
    currency = "COP"
    charge_unit = "per_night"
    amount = factory.LazyFunction(lambda: Decimal("480000"))
    created_by = factory.SelfAttribute("tourist_service.created_by")


class TravelRequestFactory(BaseFactory):
    """Una solicitud nueva con fechas exactas dentro de un mes; `flexible=True` la da con un
    período flexible y `closed=True`, cerrada porque el cliente desistió."""

    class Meta:
        model = TravelRequest

    class Params:
        flexible = factory.Trait(
            date_mode="flexible",
            departure_date=None,
            window_start=factory.LazyFunction(lambda: today() + timedelta(days=30)),
            window_end=factory.LazyFunction(lambda: today() + timedelta(days=60)),
        )
        closed = factory.Trait(
            status="closed",
            close_reason="client_declined",
            closed_at=factory.LazyFunction(lambda: datetime.now(timezone.utc)),
            closed_by=factory.SelfAttribute("created_by"),
        )

    client = factory.SubFactory(ClientFactory)
    destination = "San Andrés"
    date_mode = "exact"
    departure_date = factory.LazyFunction(lambda: today() + timedelta(days=30))
    adults = 2
    minors = 0
    trip_types = factory.LazyFunction(list)
    status = "new"
    created_by = factory.SelfAttribute("client.created_by")
    assigned_to = factory.SelfAttribute("created_by")
