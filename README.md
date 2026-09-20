# app-escapate-backend

API de Escápate. FastAPI + SQLModel + PostgreSQL, gestor de dependencias `uv`.

Ver [`AGENTS.md`](AGENTS.md) para el contexto completo y las reglas de trabajo.

## Levantar el entorno

```bash
uv sync
uv run alembic upgrade head   # cuando existan migraciones
uv run fastapi dev app/main.py
```

## Calidad de código

```bash
uv run ruff check --fix .
uv run black .
uv run pytest
```

`pre-commit` ya está instalado (`.pre-commit-config.yaml`): corre Ruff + Black en cada commit.
