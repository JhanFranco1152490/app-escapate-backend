# Escápate — Backend

Proyecto académico (UFPS). Este repo es la API **FastAPI** — un repo hermano de
`app-escapate-frontend` (Next.js). Vive normalmente junto al repo paraguas `app escapate`
(workspace: `docs/`, `specs/`, contexto completo del dominio) — pero **este archivo no
depende de que ese repo exista al lado**: quien clone solo este repo debe poder trabajar
seguro con lo que sigue.

## No negociables del proyecto (resumen — la versión completa con el porqué de cada uno
vive en `AGENTS.md` del workspace, si lo tienes al lado)

- **Commits y push: los hace la persona, nunca el agente**, salvo que se pida explícito en
  esa sesión. El agente siempre propone el mensaje de commit.
- **Dos ramas fijas `main`/`dev`.** Ramas de trabajo salen de `dev`, nunca de `main`;
  integran a `dev` por PR con **squash merge**. Nadie hace force-push a ninguna de las dos.
- **Idioma:** nombres en el código (modelos, campos, funciones, endpoints) en **inglés**;
  **comentarios de código en español, sin emojis**; mensajes de commit en **inglés**,
  formato Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`),
  resumen conciso ≤ 72 caracteres. El cuerpo del commit **solo** para el porqué que el diff
  no muestra por sí solo — nunca para narrar el qué; si no hay nada así, sin cuerpo.
- **Comentarios de código nunca mencionan specs, el repo workspace, ni rutas como
  `specs/003`** — este repo puede vivir clonado solo, sin el workspace al lado, así que esa
  referencia sería un enlace roto. Si hace falta el porqué de una decisión, se escribe
  completo en el comentario mismo.
- **Los comentarios tampoco nombran el proveedor/herramienta de turno** (Railway, Vercel,
  etc.) salvo que el código dependa de un detalle propio de ese proveedor. El mecanismo real
  (variables de entorno, convención 12-factor) es el mismo sin importar el proveedor, y
  nombrarlo de más ata el comentario a una decisión de infraestructura que puede cambiar.
  Un ejemplo con nombre de proveedor sí es válido en `.env.example`, nunca en código.
- **Toda feature con código lleva tests.** Lint/formato limpio antes de commitear (Ruff +
  Black, ya configurados con `pre-commit`).
- **Nunca commitear secretos** (`.env`, `secret_key`, credenciales de base de datos).
- **Seguridad y datos: activa desde el inicio.** Ver "Seguridad y datos" en `AGENTS.md`
  del workspace — este sistema maneja datos personales reales de clientes/viajeros y
  autenticación real de usuarios (administrador, asesores) desde el primer sprint.

## Específico de este repo

- **Entorno gestionado por `uv`.** No hay `.venv` manual que activar: cada comando corre
  con `uv run <comando>` (o `uv run python`, `uv run pytest`, etc.), y `uv sync` instala
  las dependencias declaradas en `pyproject.toml` (`uv.lock` fija las versiones exactas).
- **Estructura:** `app/` (paquete de la aplicación) — `app/main.py` (instancia de FastAPI),
  `app/core/` (config, conexión a DB), `app/models/` (modelos SQLModel), `app/schemas/`
  (schemas Pydantic de entrada/salida cuando difieran del modelo), `app/api/` (routers).
  `alembic/` para las migraciones, `tests/` para las pruebas.
- **Modelo de usuario:** aún no existe un modelo de dominio en código. El contexto ya
  llegó (`docs/CONTEXTO.md` del workspace: Administrador, Asesor comercial, Encargado de
  proveedores y alianzas, Operativo — con roles/permisos por RF-03), pero el diagrama ER
  formal todavía no — no generes la primera migración real de `User`/`Role` sin que el
  agente `arquitecto` (o el equipo) resuelva las preguntas abiertas del modelo. Cambiar el
  modelo de autenticación después de tener migraciones aplicadas es doloroso — mejor
  definirlo bien la primera vez.
- **Base de datos:** PostgreSQL (`DATABASE_URL` en `.env`, ver `app/core/config.py`).
  Driver `psycopg` 3.
- Migraciones con Alembic: `uv run alembic revision --autogenerate -m "..."` y
  `uv run alembic upgrade head`. Revisa siempre el archivo autogenerado antes de aplicarlo.

## Pendiente antes de escribir los modelos del dominio

El contexto ya está en `docs/CONTEXTO.md` del workspace (36 RF, 51 HU), pero antes de
generar la primera migración real hace falta: resolver las 5 preguntas abiertas del modelo
de datos con el agente `arquitecto`, y empezar por RF-01 a RF-03 (auth + usuarios + roles/
permisos) — es la base de la que dependen los demás módulos (CRM, cotizaciones, pagos). El
`health check` en `app/main.py` es el único endpoint real por ahora.

## Stack

FastAPI + SQLModel + Alembic + PostgreSQL, gestor `uv`. Aún sin autenticación ni modelos de
dominio en código — se añaden cuando arranque el trabajo real (empezando por auth/usuarios/
roles).
