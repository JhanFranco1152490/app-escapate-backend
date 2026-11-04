"""Columnas que repiten los modelos de todos los dominios, declaradas una sola vez."""

from enum import StrEnum

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Integer, func
from sqlmodel import Field


def in_values(column: str, enum: type[StrEnum]) -> str:
    """Condición de un CHECK que limita la columna a los valores del enum."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def primary_key():
    return Field(default=None, sa_column=Column(BigInteger, Identity(), primary_key=True))


def foreign_key(target: str, ondelete: str, nullable: bool = False, **kwargs):
    column = Column(BigInteger, ForeignKey(target, ondelete=ondelete), nullable=nullable, **kwargs)
    if nullable:
        return Field(default=None, sa_column=column)
    return Field(sa_column=column)


def version_column():
    return Field(default=None, sa_column=Column(Integer, nullable=False))


def versioned(cls) -> dict:
    # Bloqueo optimista: cada UPDATE exige que la versión en la base siga siendo la que se
    # leyó, y la sube en uno. Si otra petición guardó antes, SQLAlchemy lanza StaleDataError.
    return {"version_id_col": cls.__table__.c.version}


def timestamp(nullable: bool = False, **kwargs):
    if not nullable:
        kwargs.setdefault("server_default", func.now())
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=nullable, **kwargs),
    )
