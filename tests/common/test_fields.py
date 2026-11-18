from enum import StrEnum
from typing import Annotated

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError

from app.common.fields import fixed_choices, optional_multiline_text


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


class Note(BaseModel):
    text: Annotated[str, AfterValidator(optional_multiline_text(10))] | None = None


def note_errors(text: str) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        Note(text=text)
    return [error["msg"] for error in caught.value.errors()]


def test_a_multiline_text_keeps_its_line_breaks():
    assert Note(text="uno\ndos").text == "uno\ndos"


def test_windows_and_old_mac_line_breaks_become_a_single_line_feed():
    assert Note(text="a\r\nb\rc").text == "a\nb\nc"


def test_a_multiline_text_is_trimmed_and_empty_becomes_none():
    assert Note(text="  \n hola \n ").text == "hola"
    assert Note(text=" \n ").text is None


@pytest.mark.parametrize("character", ["\t", "\x00", "\u200b"])
def test_other_control_or_invisible_characters_are_rejected(character):
    assert note_errors(f"a{character}b") == ["Contiene caracteres que no se permiten."]


def test_the_length_is_counted_after_converting_the_line_breaks():
    # Con "\r\n" son once caracteres; con "\n", diez: caben.
    assert Note(text="abcde\r\nfghi").text == "abcde\nfghi"
    assert note_errors("abcdefghijk") == ["Máximo 10 caracteres."]
