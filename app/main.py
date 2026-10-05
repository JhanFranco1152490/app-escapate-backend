from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from app.common.errors import ErrorResponse, register_error_handlers
from app.core.config import Settings
from app.core.config import settings as default_settings

_ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}


def create_app(settings: Settings = default_settings) -> FastAPI:
    app = FastAPI(
        title="Escápate API",
        openapi_url="/api/openapi.json" if settings.debug else None,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health", include_in_schema=False)
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.openapi = lambda: _openapi(app)
    return app


def _openapi(app: FastAPI) -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version="1.0.0", routes=app.routes)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components["ErrorResponse"] = ErrorResponse.model_json_schema()
    # Los 422 se responden con la forma común; el esquema por defecto de FastAPI mentiría.
    for name in ("HTTPValidationError", "ValidationError"):
        components.pop(name, None)
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            response = operation.get("responses", {}).get("422")
            if response:
                response["content"] = {"application/json": {"schema": _ERROR_REF}}
                response["description"] = "Datos inválidos"
    app.openapi_schema = schema
    return schema


app = create_app()
