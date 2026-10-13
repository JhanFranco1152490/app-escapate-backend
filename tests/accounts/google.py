"""Google simulado: llaves RSA de prueba, id_token firmados y el endpoint de tokens."""

import time
from urllib.parse import parse_qs, urlparse

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

CLIENT_ID = "cliente-de-prueba.apps.googleusercontent.com"
GOOGLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OMIT = object()


def make_id_token(nonce: str, key=GOOGLE_KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "persona@example.com",
        "email_verified": True,
        "nonce": nonce,
        "iat": now,
        "exp": now + 300,
    } | overrides
    claims = {name: value for name, value in claims.items() if value is not OMIT}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "prueba"})


class FakeGoogle:
    def __init__(self):
        self.id_token: str | None = None
        self.status = 200
        self.error: type[Exception] | None = None
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        if self.error:
            raise self.error("Google no responde", request=request)
        self.requests.append(request)
        body = {"id_token": self.id_token} if self.id_token else {}
        return httpx2.Response(self.status, json=body)

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self.handler))


def start(client, next_path: str = "/clientes"):
    """Inicia el flujo; devuelve la respuesta, el state y el nonce enviados a Google."""
    response = client.get(
        "/api/auth/google/start", params={"next": next_path}, follow_redirects=False
    )
    query = parse_qs(urlparse(response.headers["location"]).query)
    return response, query["state"][0], query["nonce"][0]


def callback(client, **params):
    return client.get("/api/auth/google/callback", params=params, follow_redirects=False)


def redirect_error(response) -> str | None:
    values = parse_qs(urlparse(response.headers["location"]).query).get("error")
    return values[0] if values else None
