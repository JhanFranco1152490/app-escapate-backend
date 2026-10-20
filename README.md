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

`create-admin` pide nombres, apellidos, correo (Gmail personal), tipo y número de documento,
celular colombiano de 10 dígitos y contraseña. Las demás personas las registra el
administrador desde la gestión de usuarios (`/api/users`), y a cada una le llega un correo
para crear su propia contraseña.

Con `EMAIL_BACKEND=console` (el valor local) los correos no se envían: se imprimen en la
terminal del backend, con el enlace de recuperación o de invitación listo para copiar.

La búsqueda de usuarios sin tildes usa la extensión `unaccent` de PostgreSQL: la migración
la crea, así que el rol de la base necesita permiso para `CREATE EXTENSION` (en una base
local con un rol superusuario ya lo tiene).

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
