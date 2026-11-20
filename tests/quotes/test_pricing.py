from decimal import Decimal

from app.quotes.pricing import LineAmounts, cost_in_pesos, sale_price, totals
from tests.factories import QuoteFactory, QuoteItemFactory


def test_the_cost_in_pesos_is_the_unit_cost_times_the_quantity():
    assert cost_in_pesos(Decimal("450000"), 4, "COP", None) == 1_800_000


def test_dollars_are_converted_with_the_quote_rate_and_rounded_to_the_peso():
    assert cost_in_pesos(Decimal("120.50"), 2, "USD", Decimal("4000.25")) == 964_060
    assert cost_in_pesos(Decimal("120.50"), 2, "USD", None) is None


def test_the_sale_price_adds_the_markup_unless_written_by_hand():
    assert sale_price(1_800_000, Decimal("15"), None) == 2_070_000
    assert sale_price(1_000_001, Decimal("12.5"), None) == 1_125_001
    assert sale_price(1_800_000, Decimal("15"), 2_000_000) == 2_000_000
    assert sale_price(None, Decimal("15"), None) is None


def test_the_totals_leave_the_optional_services_apart():
    result = totals(
        [
            LineAmounts(cost=1_800_000, sale=2_070_000, is_optional=False),
            LineAmounts(cost=600_000, sale=690_000, is_optional=False),
            LineAmounts(cost=300_000, sale=360_000, is_optional=True),
        ],
        travelers=3,
        deposit_percent=Decimal("30"),
    )

    assert (result.cost, result.sale, result.profit) == (2_400_000, 2_760_000, 360_000)
    assert result.margin_percent == Decimal("13.04")
    assert result.optional_sale == 360_000
    assert result.per_person == 920_000
    assert result.deposit == 828_000
    assert result.missing_exchange_rate is False


def test_a_dollar_service_without_rate_is_flagged_and_left_out():
    result = totals([LineAmounts(cost=None, sale=None, is_optional=False)], 2, None)

    assert (result.sale, result.missing_exchange_rate, result.margin_percent) == (0, True, None)


def test_the_detail_answers_each_price_and_the_totals(auth_client, advisor_role, session):
    quote = QuoteFactory(adults=2, minors=0, exchange_rate=Decimal("4000"))
    QuoteItemFactory(quote=quote, unit_cost=Decimal("400000"), quantity=2)
    QuoteItemFactory(
        quote=quote, currency="USD", unit_cost=Decimal("100"), quantity=1, markup_percent=0
    )
    api = auth_client(permissions=["quotes.view"])

    detail = api.get(f"/api/quotes/{quote.id}").json()

    assert [(row["cost_in_pesos"], row["sale_price"]) for row in detail["items"]] == [
        (800_000, 920_000),
        (400_000, 400_000),
    ]
    assert detail["totals"]["sale"] == 1_320_000
    assert detail["totals"]["per_person"] == 660_000


def test_changing_the_default_markup_and_the_rate(auth_client, session):
    quote = QuoteFactory()
    api = auth_client(permissions=["quotes.view", "quotes.manage"])

    response = api.put(
        f"/api/quotes/{quote.id}/pricing",
        json={"default_markup_percent": "20", "exchange_rate": "4100.50", "expected_version": 1},
    )

    assert response.status_code == 200, response.json()
    assert (response.json()["default_markup_percent"], response.json()["exchange_rate"]) == (
        "20.00",
        "4100.50",
    )
