from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session


def constraint_name(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


@contextmanager
def database_conflicts(
    session: Session, errors: Mapping[str, Callable[[], Exception]]
) -> Iterator[None]:
    """Traduce una restricción de la base al error que daría la revisión previa del servicio.

    La base responde cuando otra petición cambió algo entre esa revisión y la escritura. Se
    reconoce por el nombre de la restricción, nunca por el mensaje, que trae el valor
    repetido y además viene en el idioma del servidor. Conviene envolver todas las
    escrituras, no solo el `commit()`: un `flush()` automático antes de una consulta también
    choca con la base.
    """
    try:
        yield
    except IntegrityError as error:
        session.rollback()
        make_error = errors.get(constraint_name(error))
        if make_error is None:
            raise
        # Sin encadenar el error original: su mensaje trae el valor repetido.
        raise make_error() from None
