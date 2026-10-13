# app-escapate-backend

API de Escápate. FastAPI + SQLModel + PostgreSQL, gestor de dependencias `uv`.

Ver [`AGENTS.md`](AGENTS.md) para la estructura, el contrato de la API y las reglas de
trabajo.

## Levantar el entorno

Requisitos: PostgreSQL local con un rol con `CREATEDB` y la base `app_escapate`, y un `.env`
copiado de `.env.example`.

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.cli create-admin   # primera cuenta, con el rol Administrador
uv run uvicorn app.main:app --reload
```

Para probar el ingreso con Google en local hace falta un cliente OAuth propio en
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (ver `.env.example`); sin él, todo lo demás
funciona y el botón de Google responde con error.

Con `DEBUG=true`, la documentación de la API está en <http://localhost:8000/api/docs>.

## Pruebas y calidad

```bash
uv run pytest --cov -q      # crea y borra sola la base app_escapate_test
uv run ruff check .
uv run black --check .
uv run alembic check
```

`pre-commit` corre Ruff y Black en cada commit (`.pre-commit-config.yaml`).
