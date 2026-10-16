import pytest

from app.common.email import render

LINK = "https://app.example.com/restablecer-contrasena#token=abc.def"


@pytest.mark.parametrize("name", ["password_reset", "invitation"])
def test_link_emails_carry_the_name_link_and_lifetime(name):
    text, html = render("accounts", name, {"name": "Laura", "link": LINK, "expires_in": "2 días"})

    for body in (text, html):
        assert "Laura" in body
        assert LINK in body
        assert "2 días" in body


@pytest.mark.parametrize("name", ["password_reset", "invitation", "password_changed"])
def test_html_escapes_the_name(name):
    context = {"name": "<script>", "link": LINK, "expires_in": "x", "date": "d", "time": "t"}

    _, html = render("accounts", name, context)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_the_change_notice_has_no_links():
    # Un aviso con un botón es justo lo que imita un phishing: este correo no lleva enlaces.
    text, html = render(
        "accounts", "password_changed", {"name": "Laura", "date": "13/10/2026", "time": "10:05"}
    )

    for body in (text, html):
        assert "13/10/2026" in body and "10:05" in body
        assert "http" not in body
    assert "<a " not in html
