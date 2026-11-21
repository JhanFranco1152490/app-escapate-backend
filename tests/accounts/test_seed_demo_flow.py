"""La carga de demostración del flujo comercial: paquete, cotizaciones, seguimientos, ventas,
reservas, costos y gastos."""

import pytest
from sqlmodel import func, select

from app import cli
from app.common.dates import today
from app.core.config import settings
from app.finance.models import ActualCost, OperatingExpense
from app.quotes.follow_up_models import AlertColor, QuoteFollowUp, alert_color
from app.quotes.models import Quote, QuoteStatus
from app.quotes.package_models import TourPackage
from app.reports.services import dashboard
from app.sales.booking_models import Booking, BookingStatus
from app.sales.models import PaymentStatus, Sale

FLOW_MODELS = (TourPackage, Quote, QuoteFollowUp, Sale, Booking, ActualCost, OperatingExpense)


@pytest.fixture
def seeded(session, monkeypatch):
    monkeypatch.setattr(settings, "allow_demo_seed", True)
    assert cli.main(["seed-demo", "--with-demo-data"], session=session) == 0
    return session


def count(session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def test_it_shows_every_stage_of_the_funnel(seeded):
    statuses = sorted(seeded.exec(select(Quote.status)).all())
    assert statuses == sorted(
        [QuoteStatus.ACCEPTED, QuoteStatus.ACCEPTED, QuoteStatus.SENT, QuoteStatus.DRAFT]
    )
    day = today()
    pending = seeded.exec(select(QuoteFollowUp).where(QuoteFollowUp.status == "pending")).all()
    colors = {alert_color(follow_up.due_date, day) for follow_up in pending}
    assert colors == {AlertColor.RED, AlertColor.YELLOW, AlertColor.GREEN}


def test_one_sale_owes_a_balance_and_the_other_is_paid(seeded):
    sales = seeded.exec(select(Sale)).all()

    assert sorted(sale.payment_status for sale in sales) == sorted(
        [PaymentStatus.PARTIAL, PaymentStatus.PAID]
    )
    paid = next(sale for sale in sales if sale.payment_status == PaymentStatus.PAID)
    assert paid.balance == 0


def test_bookings_are_prepared_with_some_confirmed(seeded):
    statuses = seeded.exec(select(Booking.status)).all()

    assert BookingStatus.CONFIRMED in statuses
    assert BookingStatus.REQUESTED in statuses
    assert count(seeded, ActualCost) > 0


def test_the_dashboard_is_not_empty(seeded):
    board = dashboard(seeded)

    assert board.quotes_draft == 1
    assert board.quotes_sent == 1
    assert board.follow_ups_red == 1
    assert board.follow_ups_yellow == 1


def test_running_it_twice_duplicates_nothing(seeded, capsys):
    counts = [count(seeded, model) for model in FLOW_MODELS]
    capsys.readouterr()

    assert cli.main(["seed-demo", "--with-demo-data"], session=seeded) == 0

    assert [count(seeded, model) for model in FLOW_MODELS] == counts
    assert "creado" not in capsys.readouterr().out.replace("omitido", "")
