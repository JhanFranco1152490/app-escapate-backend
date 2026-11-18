import pytest

from app.travel_requests.codes import format_code, parse_code


@pytest.mark.parametrize(
    "request_id, code", [(1, "SOL-0001"), (231, "SOL-0231"), (12345, "SOL-12345")]
)
def test_the_code_has_at_least_four_digits(request_id, code):
    assert format_code(request_id) == code


@pytest.mark.parametrize(
    "text", ["SOL-0231", "sol-0231", "SOL-231", "Sol231", "231", "0231", " SOL - 0231 "]
)
def test_any_way_of_writing_the_code_gives_the_id(text):
    assert parse_code(text) == 231


@pytest.mark.parametrize(
    "text",
    [
        "",
        "SOL-",
        "0000",
        "San Andrés",
        "SOL-23a",
        "231-",
        "1" * 19,
        "-5",
        "12.5",
    ],
)
def test_anything_that_is_not_a_code_gives_nothing(text):
    assert parse_code(text) is None


def test_the_largest_accepted_code_fits_in_the_database():
    assert parse_code("9" * 18) == int("9" * 18)
