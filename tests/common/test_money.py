from decimal import Decimal

import pytest

from app.common.money import apply_percentage, round_to_peso


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("1250.5"), 1251),
        (Decimal("1250.49"), 1250),
        (Decimal("1250"), 1250),
        (Decimal("-0.5"), -1),
    ],
)
def test_rounds_to_the_nearest_peso_with_halves_up(value, expected):
    assert round_to_peso(value) == expected


def test_float_is_rejected_because_it_already_lost_precision():
    with pytest.raises(TypeError):
        round_to_peso(0.1 + 0.2)


@pytest.mark.parametrize(
    "amount, percentage, expected",
    [
        (1_000_000, Decimal("12.50"), 125_000),
        (999, Decimal("33.33"), 333),
        (0, Decimal("15"), 0),
    ],
)
def test_applies_a_percentage_and_rounds_once(amount, percentage, expected):
    assert apply_percentage(amount, percentage) == expected
