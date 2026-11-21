"""Ventas de demostración: las cotizaciones aceptadas de demostración, con sus abonos y el
estado de sus reservas. Todo inventado.

Los abonos van en % del precio de la venta, que sale del cálculo de la cotización: así no hay
que repetir aquí sus números, y una venta queda con saldo y la otra pagada.
"""

from dataclasses import dataclass

from app.sales.booking_models import BookingStatus


@dataclass(frozen=True)
class DemoPayment:
    percent: int
    paid_in: int
    method: str
    reference: str | None = None


@dataclass(frozen=True)
class DemoBooking:
    # El nombre del servicio de la cotización.
    name: str
    status: BookingStatus
    confirmation_code: str | None = None


@dataclass(frozen=True)
class DemoSale:
    # La cotización de demostración que se vende (ver DEMO_QUOTES).
    client_document: tuple[str, str]
    destination: str
    payments: tuple[DemoPayment, ...]
    bookings: tuple[DemoBooking, ...] = ()
    notes: str | None = None


DEMO_SALES: tuple[DemoSale, ...] = (
    DemoSale(
        ("CC", "1000000101"),
        "San Andrés",
        payments=(DemoPayment(40, -2, "transfer", "DEMO-TRF-0001"),),
        bookings=(
            DemoBooking(
                "Tiquetes Cúcuta – San Andrés ida y regreso",
                BookingStatus.CONFIRMED,
                "DEMO-PNR01",
            ),
            DemoBooking("Hotel frente al mar, habitación triple", BookingStatus.REQUESTED),
        ),
        notes="El saldo se paga 15 días antes del viaje.",
    ),
    DemoSale(
        ("NIT", "9000001028"),
        "Medellín",
        payments=(
            DemoPayment(50, -10, "transfer", "DEMO-TRF-0002"),
            DemoPayment(50, -1, "card", "DEMO-TC-0003"),
        ),
        bookings=(
            DemoBooking(
                "Tiquetes Bogotá – Medellín ida y regreso", BookingStatus.CONFIRMED, "DEMO-PNR02"
            ),
            DemoBooking(
                "Hotel ejecutivo, tres habitaciones dobles", BookingStatus.CONFIRMED, "DEMO-H-77"
            ),
        ),
    ),
)
