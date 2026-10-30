"""Expresiones de SQL para buscar y ordenar texto escrito por personas."""

from sqlalchemy import ColumnElement, and_, func

from app.common.identifiers import normalize_document

# Más palabras que esto no cambian de forma útil el resultado y alargan la consulta.
MAX_SEARCH_WORDS = 5
_ESCAPE = "\\"


def folded(expression):
    """Sin tildes y en minúsculas. Primero se quitan las tildes: pasar a minúsculas una letra
    acentuada depende de la configuración regional de la base y puede dejarla igual.

    Necesita la extensión `unaccent` de PostgreSQL.
    """
    return func.lower(func.unaccent(expression))


def escape_like(text: str) -> str:
    """Hace literales los comodines de LIKE, para que lo escrito se busque tal cual."""
    return (
        text.replace(_ESCAPE, _ESCAPE * 2).replace("%", f"{_ESCAPE}%").replace("_", f"{_ESCAPE}_")
    )


def has_every_word(expression, text: str) -> ColumnElement[bool]:
    """Cada palabra de `text` aparece en `expression`, en cualquier orden y sin tildes."""
    words = text.split()[:MAX_SEARCH_WORDS]
    return and_(
        *(
            folded(expression).like(folded(f"%{escape_like(word)}%"), escape=_ESCAPE)
            for word in words
        )
    )


def starts_with(expression, text: str) -> ColumnElement[bool]:
    return expression.like(f"{escape_like(text)}%", escape=_ESCAPE)


def contains(expression, text: str) -> ColumnElement[bool]:
    return expression.like(f"%{escape_like(text)}%", escape=_ESCAPE)


def name_or_document(name, document_number, text: str) -> list[ColumnElement[bool]]:
    """Las formas de encontrar a una persona por lo que se escribe en el buscador: cada palabra
    en su nombre, o el comienzo de su documento ya normalizado (sin puntos ni guiones)."""
    conditions = [has_every_word(name, text)]
    document = normalize_document(text)
    if document:
        conditions.append(starts_with(document_number, document))
    return conditions
