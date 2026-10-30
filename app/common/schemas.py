from pydantic import BaseModel, ConfigDict


class InputSchema(BaseModel):
    """Cuerpo de una petición: un campo que no está declarado es un error, no se ignora."""

    model_config = ConfigDict(extra="forbid")


class OutputSchema(BaseModel):
    """Respuesta armada desde un modelo de la base."""

    model_config = ConfigDict(from_attributes=True)
