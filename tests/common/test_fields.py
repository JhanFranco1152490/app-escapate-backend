from enum import StrEnum

import pytest
from pydantic import BaseModel, ValidationError

from app.common.fields import fixed_choices


class Color(StrEnum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


Colors = fixed_choices(
    Color,
    unknown="No es un color válido.",
    repeated="Hay un color repetido.",
    required="Elige al menos un color.",
)
OptionalColors = fixed_choices(Color, unknown="No es un color válido.", repeated="Repetido.")


class Required(BaseModel):
    colors: Colors


class Optional(BaseModel):
    colors: OptionalColors = []


def errors(model: type[BaseModel], colors) -> list[tuple[tuple, str]]:
    with pytest.raises(ValidationError) as caught:
        model(colors=colors)
    return [(error["loc"], error["msg"]) for error in caught.value.errors()]


def test_choices_come_back_in_the_order_of_the_enum():
    assert Required(colors=["blue", "red"]).colors == [Color.RED, Color.BLUE]


def test_an_unknown_choice_is_reported_on_the_field_not_on_its_position():
    assert errors(Required, ["red", "pink"]) == [(("colors",), "No es un color válido.")]


def test_a_repeated_choice_is_rejected():
    assert errors(Required, ["red", "red"]) == [(("colors",), "Hay un color repetido.")]


def test_an_empty_list_is_rejected_when_required():
    assert errors(Required, []) == [(("colors",), "Elige al menos un color.")]


def test_an_empty_list_is_accepted_when_not_required():
    assert Optional(colors=[]).colors == []
    assert Optional().colors == []


def test_more_items_than_choices_is_rejected():
    assert errors(Required, ["red", "green", "blue", "red"])[0][0] == ("colors",)
