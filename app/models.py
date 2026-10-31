"""Importa los modelos de todos los dominios para registrarlos en SQLModel.metadata."""

from sqlmodel import SQLModel

import app.accounts.models  # noqa: F401
import app.clients.models  # noqa: F401
import app.suppliers.models  # noqa: F401

metadata = SQLModel.metadata
