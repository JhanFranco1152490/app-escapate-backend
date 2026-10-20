import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    detail: str
    code: str
    fields: dict[str, list[str]] = {}


def error_responses(*statuses: int) -> dict:
    """Los códigos de error que un endpoint puede responder, para su OpenAPI."""
    return {status_code: {"model": ErrorResponse} for status_code in statuses}


class ApiError(Exception):
    status_code = 400
    code = "error"
    detail = "No se pudo completar la solicitud."

    def __init__(self, detail: str | None = None, fields: dict[str, list[str]] | None = None):
        self.detail = detail or self.detail
        self.fields = fields or {}
        super().__init__(self.code)


class NotAuthenticated(ApiError):
    status_code, code, detail = 401, "not_authenticated", "Debes iniciar sesión."


class AuthenticationFailed(ApiError):
    status_code, code, detail = 401, "authentication_failed", "Tu sesión venció."


class PermissionDenied(ApiError):
    status_code, code, detail = 403, "permission_denied", "No tienes permiso para esto."


class NotFound(ApiError):
    status_code, code, detail = 404, "not_found", "No encontramos lo que buscas."


class StaleVersion(ApiError):
    status_code, code = 409, "stale_version"
    detail = "Alguien más guardó cambios. Recarga para ver la versión actual."


def error_response(
    status_code: int, code: str, detail: str, fields: dict[str, list[str]] | None = None
) -> JSONResponse:
    # no-store aquí y no solo en el middleware: el 500 se arma por fuera de los middlewares.
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "fields": fields or {}},
        headers={"Cache-Control": "no-store"},
    )


def _field_name(location: tuple) -> str:
    return str(location[-1]) if location else "non_field_errors"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.detail, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        fields: dict[str, list[str]] = {}
        for error in exc.errors():
            fields.setdefault(_field_name(error["loc"]), []).append(error["msg"])
        return error_response(422, "validation_error", "Revisa los datos enviados.", fields)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, NotFound.code, NotFound.detail)
        if exc.status_code == 405:
            return error_response(405, "method_not_allowed", "Método no permitido.")
        return error_response(exc.status_code, "error", ApiError.detail)

    @app.exception_handler(StaleDataError)
    async def on_stale_data(request: Request, exc: StaleDataError):
        return error_response(409, StaleVersion.code, StaleVersion.detail)

    @app.exception_handler(RateLimitExceeded)
    async def on_rate_limit(request: Request, exc: RateLimitExceeded):
        return error_response(429, "throttled", "Demasiados intentos. Espera un momento.")

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception):
        # Solo la clase y la traza: el mensaje de la excepción puede traer un correo o un
        # documento.
        trace = "".join(traceback.format_tb(exc.__traceback__))
        logger.error("Unhandled %s\n%s", type(exc).__name__, trace)
        return error_response(500, "internal_error", "Ocurrió un error inesperado.")
