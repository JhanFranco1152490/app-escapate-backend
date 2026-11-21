"""Cada endpoint de cotizaciones, seguimientos, paquetes, ventas, reservas, finanzas y reportes
exige su permiso: sin ninguno responde 403, y con solo los de ver, toda escritura también."""

import re

import pytest

from app.main import create_app

PREFIXES = (
    "/api/quotes",
    "/api/follow-ups",
    "/api/packages",
    "/api/sales",
    "/api/bookings",
    "/api/costs",
    "/api/expenses",
    "/api/finance",
    "/api/reports",
)
VIEW_PERMISSIONS = [
    "quotes.view",
    "sales.view",
    "finance.view",
    "reports.view",
    "clients.view",
    "suppliers.view",
    "tourist_services.view",
    "travel_requests.view",
]


def _routes() -> list[tuple[str, str]]:
    # Del esquema: los routers incluidos no se ven como rutas sueltas de la app.
    paths = create_app().openapi()["paths"]
    routes = []
    for template, operations in paths.items():
        if not template.startswith(PREFIXES):
            continue
        # Cualquier id sirve: el permiso se revisa antes de buscar el registro.
        path = re.sub(r"\{[a-z_]+\}", "1", template.replace("{kind}", "sales"))
        routes.extend((method.upper(), path) for method in operations)
    return routes


ROUTES = _routes()
WRITES = [(method, path) for method, path in ROUTES if method != "GET"]


def test_the_list_covers_every_module():
    assert len(ROUTES) > 40
    assert {path.split("/")[2] for _, path in ROUTES} >= {
        "quotes",
        "follow-ups",
        "packages",
        "sales",
        "bookings",
        "costs",
        "expenses",
        "finance",
        "reports",
    }


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_without_permissions_it_answers_403(auth_client, method, path):
    response = auth_client().request(method, path)

    assert response.status_code == 403, response.json()


@pytest.mark.parametrize(("method", "path"), WRITES)
def test_with_only_view_permissions_writes_answer_403(auth_client, method, path):
    response = auth_client(permissions=VIEW_PERMISSIONS).request(method, path)

    assert response.status_code == 403, response.json()
