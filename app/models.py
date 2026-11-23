"""Importa los modelos de todos los dominios para registrarlos en SQLModel.metadata."""

from sqlmodel import SQLModel

import app.accounts.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.clients.models  # noqa: F401
import app.finance.models  # noqa: F401
import app.quotes.follow_up_models  # noqa: F401
import app.quotes.models  # noqa: F401
import app.quotes.package_models  # noqa: F401
import app.sales.booking_models  # noqa: F401
import app.sales.models  # noqa: F401
import app.suppliers.models  # noqa: F401
import app.suppliers.tourist_service_models  # noqa: F401
import app.travel_requests.models  # noqa: F401

metadata = SQLModel.metadata
