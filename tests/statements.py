from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event


@contextmanager
def recorded_statements(session) -> Iterator[list[str]]:
    """Las sentencias SQL que la sesión manda a la base dentro del bloque, para probar que una
    consulta no hace una por fila."""
    statements: list[str] = []

    def record(connection, cursor, statement, *args):
        statements.append(statement)

    connection = session.get_bind()
    event.listen(connection, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", record)
