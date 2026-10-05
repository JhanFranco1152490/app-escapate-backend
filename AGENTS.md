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
- **Estructura por dominio:**

  ```
  app/
  ├── main.py            create_app(): routers, manejadores de errores, CORS, CSRF, límite
  ├── models.py          importa los modelos de cada dominio (lo que ve Alembic)
  ├── core/              configuración y conexión, sin lógica de negocio
  │   ├── config.py      Settings (pydantic-settings, lee .env)
  │   ├── db.py          engine + get_session
  │   ├── rate_limit.py  limiter de slowapi
  │   └── security/      passwords, tokens (JWT), cookies, csrf, network (client_ip)
  ├── common/            transversal, sin modelos: errors, pagination, money, dates, email
  └── <dominio>/         models.py, schemas.py, services.py, router.py, templates/email/
  tests/
  ├── conftest.py        base de prueba, sesión con rollback, app, client, csrf_client
  ├── database.py        crear/borrar la base de prueba y su protección de nombre
  ├── http.py            attach_csrf(client)
  ├── factories.py       BaseFactory (factory-boy)
  └── <dominio>/test_*.py
  ```

  Un dominio nunca importa de la carpeta de otro, salvo `accounts` para la sesión y los
  permisos; lo que usan dos dominios sube a `common/`. Cada dominio nuevo agrega su
  `import` en `app/models.py` para que Alembic vea sus tablas.
- **Modelo de usuario:** aún no existe un modelo de dominio en código. El contexto ya
  llegó (`docs/CONTEXTO.md` del workspace: Administrador, Asesor comercial, Encargado de
  proveedores y alianzas, Operativo — con roles/permisos por RF-03), pero el diagrama ER
  formal todavía no — no generes la primera migración real de `User`/`Role` sin que el
  agente `arquitecto` (o el equipo) resuelva las preguntas abiertas del modelo. Cambiar el
  modelo de autenticación después de tener migraciones aplicadas es doloroso — mejor
  definirlo bien la primera vez.
- **Base de datos:** PostgreSQL (`DATABASE_URL` en `.env`, ver `app/core/config.py`).
  Driver `psycopg` 3. La configuración acepta `postgres://` y `postgresql://` (como la
  entregan los proveedores) y la normaliza a `postgresql+psycopg://`.
- Migraciones con Alembic: `uv run alembic revision --autogenerate -m "..."` y
  `uv run alembic upgrade head`. Revisa siempre el archivo autogenerado antes de aplicarlo.
- **Variables de entorno:** ver `.env.example` (local) y la tabla de "Despliegue" de la spec
  de base técnica en el workspace (Railway).
- **Levantar:** `uv run uvicorn app.main:app --reload`. Con `DEBUG=true` el esquema está en
  `/api/openapi.json` y Swagger en `/api/docs`; sin `DEBUG` no se publican.

## Contrato de la API

- Todo bajo `/api/`, sin barra final, salvo `/health`.
- **Errores:** siempre una subclase de `ApiError` (`app/common/errors.py`). Los manejadores
  arman `{"detail", "code", "fields"}`; nunca se devuelve un `JSONResponse` de error a mano.
  El 422 de FastAPI sale como `validation_error`, el `StaleDataError` del bloqueo optimista
  como `409 stale_version` y el límite de solicitudes como `429 throttled`. Un 500 se
  registra solo con la clase de la excepción y su traza, nunca con su mensaje.
- **Listados:** `response_model=Page[Esquema]` + `Depends(page_params)` + `paginate(...)` de
  `app/common/pagination.py`. El servicio pone un orden estable (último criterio `id`).
- **Entrada:** esquemas Pydantic con `model_config = ConfigDict(extra="forbid")`.
- **CSRF:** dependencia de toda la app; toda mutación bajo `/api/` exige `X-CSRF-Token`
  igual a la cookie `escapate_csrf` (`GET /api/auth/csrf`). No hay que declararlo por
  endpoint.
- **Cookies:** sus nombres, rutas y flags solo se conocen en `app/core/security/cookies.py`.
- **IP del cliente:** solo `client_ip()` (`app/core/security/network.py`) lee
  `X-Forwarded-For`, según `TRUSTED_PROXY_COUNT`.
- **Límite de solicitudes:** `@limiter.limit(...)` de `app/core/rate_limit.py`; el endpoint
  declara `request: Request`.
- **Correo:** `send_email(to, subject, domain, name, context)` de `app/common/email.py`, con
  plantillas `<dominio>/templates/email/<name>.txt|.html`. Cualquier fallo del proveedor
  sale como `EmailDeliveryError`.

## Reglas de diseño del código

- **Capas en una sola dirección:** routers (HTTP) → services (reglas y transacciones) →
  modelos. Un router no tiene lógica de negocio; un servicio no arma respuestas HTTP ni lee
  el request.
- **Una transacción por petición:** el servicio hace sus escrituras y termina con un solo
  `session.commit()`. Nunca `with session.begin():` en un servicio (falla si una dependencia
  ya leyó de la base en la misma petición).
- **Fecha de hoy:** `app/common/dates.today()` (Bogotá), nunca `date.today()`.
- **Una responsabilidad por archivo**, ~250 líneas por módulo como referencia: un módulo que
  crece se vuelve paquete (`services/__init__.py` + un archivo por tema) sin cambiar quién lo
  importa.
- **No duplicar.** La segunda vez que aparece algo se extrae; un dominio nunca importa de la
  carpeta de otro — si dos lo necesitan, sube a lo común.
- **Dinero en pesos enteros, sin centavos, nunca `float`.** Lo que produce fracciones
  (márgenes, comisiones) se calcula con `Decimal` y se redondea al peso solo con
  `app/common/money.py` (`round_to_peso`, `apply_percentage`).
- **Elegir la mejor opción, no la librería por defecto.** Ante una necesidad técnica se
  comparan las alternativas reales (lo que trae FastAPI/SQLModel, una librería, código
  propio) y se deja escrito lo elegido y lo descartado.

## Pruebas

- PostgreSQL real, nunca SQLite. Cada corrida crea la base `app_escapate_test`, aplica las
  migraciones (sube, baja y vuelve a subir) y la borra al terminar; el rol local necesita
  `CREATEDB`. El `conftest` se niega a correr si `TEST_DATABASE_URL` no termina en `_test`.
- Cada test corre en una transacción que se revierte: el `commit()` de un servicio libera un
  savepoint, no deja datos para el siguiente test.
- Fixtures: `session`, `app`, `client` (sin sesión, https) y `csrf_client` (con token CSRF,
  para mutaciones). Rutas de prueba: un `APIRouter` en el archivo del test, incluido en el
  `app` del fixture.
- Fábricas en `tests/factories.py` sobre `BaseFactory`. Correos `@example.com`, nunca datos
  personales reales.
- `filterwarnings = ["error"]`: una advertencia rompe la suite; se corrige la causa, no se
  silencia.

## Antes de proponer un PR

El agente corre y deja en verde, y si algo falla lo corrige o lo dice en el PR:

1. `uv run pytest --cov -q`
2. `uv run ruff check .`
3. `uv run black --check .`
4. `uv run alembic check` (con la base de datos local encendida): no quedan cambios de
   modelos sin migración.
5. Revisar el diff completo buscando bugs: casos borde, código duplicado, datos personales
   en logs o pruebas, tests que no afirman nada.

## Trampas conocidas

- **`alembic` es librería, no la carpeta:** la carpeta `alembic/` hace que ruff tome la
  librería como código propio; por eso `known-third-party = ["alembic"]` en `pyproject.toml`.
- **Límite de solicitudes en las pruebas:** los contadores viven en memoria; el fixture
  `reset_rate_limits` los limpia antes de cada test. Si se agrega otro `Limiter`, también.
- **Starlette 1.6** emitía una advertencia de `anyio` en el `TestClient`; con
  `filterwarnings = error` rompe la colección. Mantener Starlette ≥ 1.7.
- **`fastapi dev` no está instalado** (necesita `fastapi[standard]`): se levanta con
  `uvicorn`.
- **Un 500 llega al navegador sin cabeceras CORS:** Starlette arma el 500 en su middleware
  más externo, por fuera de `CORSMiddleware`, así que desde otro subdominio el frontend lo ve
  como un fallo de red y no como `internal_error`. La respuesta sí tiene la forma común (se
  ve con `curl` o en el log); no confundirlo con un problema de CORS de la configuración.

## Pendiente antes de escribir los modelos del dominio

El contexto ya está en `docs/CONTEXTO.md` del workspace (36 RF, 51 HU), pero antes de
generar la primera migración real hace falta: resolver las 5 preguntas abiertas del modelo
de datos con el agente `arquitecto`, y empezar por RF-01 a RF-03 (auth + usuarios + roles/
permisos) — es la base de la que dependen los demás módulos (CRM, cotizaciones, pagos). Los
únicos endpoints reales por ahora son `/health` y `GET /api/auth/csrf`.

## Stack

FastAPI + SQLModel + Alembic + PostgreSQL, gestor `uv`. Contraseñas con `pwdlib` (Argon2id),
JWT con PyJWT, recuperación con `itsdangerous`, límite con `slowapi`, correo con Jinja2 +
`httpx2`. La base técnica está lista; aún sin modelos de dominio ni login — se añaden con
`features/001` (autenticación).
