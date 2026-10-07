from pathlib import Path

import httpx2
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

APP_DIR = Path(__file__).resolve().parents[1]
_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10

# Autoescape solo en .html: en el .txt escapar convertiría el & de los enlaces en &amp;.
_templates = Environment(
    loader=FileSystemLoader(APP_DIR),
    autoescape=select_autoescape(enabled_extensions=("html",), default=False),
)


class EmailDeliveryError(Exception):
    """El proveedor no aceptó el correo. El mensaje nunca incluye al destinatario."""


def render(domain: str, name: str, context: dict) -> tuple[str, str]:
    base = f"{domain}/templates/email/{name}"
    text = _templates.get_template(f"{base}.txt").render(context)
    html = _templates.get_template(f"{base}.html").render(context)
    return text, html


def send_email(to: str, subject: str, domain: str, name: str, context: dict) -> None:
    text, html = render(domain, name, context)
    if settings.email_backend == "resend":
        _send_with_resend(to, subject, text, html)
    else:
        _print_to_console(to, subject, text)


def _print_to_console(to: str, subject: str, text: str) -> None:
    print(f"--- Correo (no enviado) ---\nPara: {to}\nAsunto: {subject}\n\n{text}")


def _http_client() -> httpx2.Client:
    return httpx2.Client(timeout=_TIMEOUT_SECONDS)


def _send_with_resend(to: str, subject: str, text: str, html: str) -> None:
    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "text": text,
        "html": html,
    }
    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    try:
        with _http_client() as client:
            response = client.post(_RESEND_URL, json=payload, headers=headers)
    except httpx2.TransportError as exc:
        raise EmailDeliveryError(f"email delivery failed: {type(exc).__name__}") from exc
    if not response.is_success:
        raise EmailDeliveryError(f"email delivery failed with status {response.status_code}")
