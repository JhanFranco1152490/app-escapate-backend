"""Expresiones de SQL para buscar y ordenar texto escrito por personas."""

from sqlalchemy import func


def folded(expression):
    """Sin tildes y en minúsculas. Primero se quitan las tildes: pasar a minúsculas una letra
    acentuada depende de la configuración regional de la base y puede dejarla igual.

    Necesita la extensión `unaccent` de PostgreSQL.
    """
    return func.lower(func.unaccent(expression))
