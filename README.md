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
uv run uvicorn app.main:app --reload
```

Con `DEBUG=true`, la documentación de la API está en <http://localhost:8000/api/docs>.

## Pruebas y calidad

```bash
uv run pytest --cov -q      # crea y borra sola la base app_escapate_test
uv run ruff check .
uv run black --check .
uv run alembic check
```

`pre-commit` corre Ruff y Black en cada commit (`.pre-commit-config.yaml`).
