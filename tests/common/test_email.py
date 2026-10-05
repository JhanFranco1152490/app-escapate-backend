import json

import httpx2
import pytest

from app.common import email
from app.core.config import settings

LINK = "https://app.example.com/restablecer?uid=1&token=abc"


def send(**context):
    email.send_email(
        to="ana@example.com",
        subject="Prueba",
        domain="accounts",
        name="example",
        context={"name": "Ana", "link": LINK, **context},
    )


def test_text_template_keeps_ampersands_in_links():
    text, _ = email.render("accounts", "example", {"name": "Ana", "link": LINK})

    assert LINK in text


def test_html_template_escapes_the_context():
    _, html = email.render("accounts", "example", {"name": "<script>", "link": LINK})

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_console_backend_prints_without_any_request(monkeypatch, capsys):
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(email, "_http_client", lambda: pytest.fail("no debe usar la red"))

    send()

    assert "Prueba" in capsys.readouterr().out


@pytest.fixture
def provider(monkeypatch):
    requests = []
    status = {"code": 200}

    def handler(request):
        requests.append(request)
        return httpx2.Response(status["code"], json={"id": "msg"})

    monkeypatch.setattr(settings, "email_backend", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(
        email, "_http_client", lambda: httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    return requests, status


def test_provider_backend_posts_the_message(provider):
    requests, _ = provider

    send()

    assert len(requests) == 1
    request = requests[0]
    assert request.headers["authorization"] == "Bearer re_test"
    body = json.loads(request.content)
    assert body["to"] == ["ana@example.com"]
    assert body["from"] == settings.email_from
    assert body["subject"] == "Prueba"
    assert LINK in body["text"]
    assert "Abrir enlace" in body["html"]


@pytest.mark.parametrize("error", [httpx2.ConnectError, httpx2.ReadTimeout])
def test_unreachable_provider_is_a_delivery_error(monkeypatch, provider, error):
    def handler(request):
        raise error("unreachable", request=request)

    monkeypatch.setattr(
        email, "_http_client", lambda: httpx2.Client(transport=httpx2.MockTransport(handler))
    )

    with pytest.raises(email.EmailDeliveryError):
        send()


def test_provider_failure_raises_without_the_recipient(provider):
    _, status = provider
    status["code"] = 500

    with pytest.raises(email.EmailDeliveryError) as error:
        send()

    assert "example.com" not in str(error.value)
