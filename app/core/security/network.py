from fastapi import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    """IP del cliente. Es el único lugar que interpreta X-Forwarded-For."""
    direct = request.client.host if request.client else ""
    count = settings.trusted_proxy_count
    if count <= 0:
        return direct
    # Cada proxy de confianza agrega una entrada al final; las de la izquierda las pudo
    # escribir el propio cliente, así que se cuenta desde la derecha.
    header = request.headers.get("x-forwarded-for", "")
    forwarded = [part.strip() for part in header.split(",") if part.strip()]
    if len(forwarded) < count:
        return direct
    return forwarded[-count]
