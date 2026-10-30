"""Ayudas para las pruebas que corren con conexiones reales al mismo tiempo."""

import time

from sqlalchemy import text

_WAITING_ON_A_LOCK = "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"


def wait_until_blocked(engine, waiting: int) -> None:
    """Espera a que `waiting` transacciones queden detenidas esperando un bloqueo."""
    deadline = time.monotonic() + 10
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            blocked = connection.execute(text(_WAITING_ON_A_LOCK)).scalar_one()
            # PostgreSQL guarda una foto de pg_stat_activity por transacción: sin cerrarla,
            # cada vuelta vería lo mismo que la primera.
            connection.rollback()
            if blocked >= waiting:
                return
            time.sleep(0.05)
    raise AssertionError("las transacciones nunca quedaron esperando el bloqueo")
