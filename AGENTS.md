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

  Cada dominio nuevo agrega su `import` en `app/models.py` para que Alembic vea sus tablas.
- **Dependencias entre dominios en una sola dirección y declaradas.** Un dominio puede
  importar de otro solo si está en la tabla de abajo, si el otro no importa de él (sin
  ciclos) y solo de su capa pública: sus `services/` y `models.py` (para claves foráneas y
  tipos), nunca su `router`. Todos pueden usar de `accounts` la sesión y los permisos
  (`CurrentUser`, `require_permission`) sin declararlo. Lo que dos dominios comparten sin
  depender uno del otro sube a `common/`. Cada feature que agrega una dependencia agrega su
  fila en el mismo PR.

  | Dominio    | Puede importar de |
  | ---------- | ----------------- |
  | `accounts` | —                 |

- **Cuentas y acceso (`app/accounts/`):**
  - `UserAccount` (tabla `user_account`: `user` es palabra reservada en PostgreSQL) con un
    solo `Role`; los permisos del rol en `RolePermission`, como texto validado contra el
    registro `app/accounts/permissions.py`.
  - Dos formas de entrar: tipo y número de documento + contraseña (`POST /api/auth/login`)
    y Google con el Gmail personal (`/api/auth/google/start` y `/callback`). Google nunca
    crea cuentas: solo entra quien el administrador registró, y se vincula por `sub`.
  - La sesión es común a las dos: `services/sessions.py` emite, rota y revoca los refresh
    tokens (máximo 3 sesiones por cuenta), registra cada ingreso en `login_event` (se
    guardan 90 días) y actualiza `last_activity_at`. El access token lleva `sid` (el `jti`
    de su refresh token) y `get_current_user` comprueba en cada petición que esa sesión siga
    abierta: logout, límite de sesiones o robo lo invalidan al instante. En las pruebas, un
    cliente autenticado sale de `auth_client` (abre una sesión real); un access token armado
    a mano con `create_token` sin `session_id` se rechaza.
  - El bloqueo por intentos fallidos cuenta por pareja documento + IP (5) y, aparte, por
    documento en todas las IP (20, fila de `login_attempt` con `ip = "*"`); los fallos más
    viejos que 15 minutos dejan de sumar.
  - Documento, correo y celular se normalizan solo con `app/accounts/identifiers.py`; la
    política de contraseñas vive solo en `app/accounts/passwords.py`. Los datos de una
    persona (nombres, apellidos, correo, documento, celular) se validan solo con `UserInput`
    de `schemas.py`, que usan la API y `create-admin`: cada tipo normaliza y valida en el
    mismo paso, con mensajes en español. El nombre completo no se guarda: `full_name` es una
    propiedad de `UserAccount`.
  - Endpoint protegido: `Depends(require_permission("dominio.accion"))`; la cuenta de la
    sesión, con `CurrentUser`.
  - Primera cuenta (o respaldo si el único administrador pierde el acceso):
    `uv run python -m app.cli create-admin` (pide nombres, apellidos, correo, documento,
    celular y contraseña).
  - Gestión de usuarios (`users_router.py`, permisos `users.view` y `users.manage`, que la
    migración asigna al rol Administrador): `services/user_queries.py` lee (lista con
    búsqueda sin tildes, ficha, ingresos, roles) y `services/user_management.py` escribe
    (alta, edición, desactivar y activar, reenviar invitación, desvincular Google). Reglas
    que no se repiten en otro lado:
    - Nunca se borra un usuario: se desactiva, lo que cierra todas sus sesiones.
    - Nadie se desactiva a sí mismo y siempre queda al menos una persona activa cuyo rol
      tenga `users.manage`; la regla bloquea las filas en orden de `id` para que dos
      desactivaciones simultáneas se esperen y no se bloqueen entre sí.
    - El correo con la invitación se envía después del `commit()`; si falla, la cuenta
      queda creada y la respuesta trae `invitation_sent: false`.
    - Las restricciones únicas de la base (correo, documento, celular) se traducen al mismo
      error de campo repetido por el nombre de la restricción, nunca por su mensaje, que
      trae el valor.
    - La búsqueda usa la extensión `unaccent` de PostgreSQL (la crea la migración).
  - Crear una contraseña desde un enlace (recuperación, 30 min; invitación, 72 h):
    `services/reset_tokens.py` firma el token sin guardarlo (deja de valer al cambiar la
    contraseña o el correo) y `services/password_reset.py` lo usa. Los correos que salen
    después de responder van como `PendingEmail` en `BackgroundTasks`: nunca se pasa la
    sesión de base de datos de la petición a una tarea en segundo plano. Otros dominios
    invitan a alguien con `password_reset.send_invitation(user)`.
  - El bloqueo por intentos vive solo en `services/lockout.py`.
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
- **No duplicar.** La segunda vez que aparece algo se extrae; lo que dos dominios
  comparten sin depender uno del otro sube a lo común (las dependencias entre dominios van
  declaradas, ver "Estructura por dominio").
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
- En `tests/accounts/`: `sent` captura los correos que la aplicación intenta enviar,
  `email_down` hace fallar al proveedor, `advisor_role` y `administrator_role` son los roles
  sembrados, y `helpers.py` trae los datos de una persona nueva (`NEW_USER`) y
  `second_client(app)` para simular otro navegador. Un servicio que pagina se prueba con
  `fake_request()` de `tests/http.py`.
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
- **Sesión de las fábricas:** asignar `BaseFactory._meta.sqlalchemy_session` no llega a las
  subclases (cada una copia sus opciones al crearse). Las fábricas toman la sesión de la
  prueba con `sqlalchemy_session_factory`; el fixture `session` la fija con `use_session`.
- **Migraciones autogeneradas:** revisar los tipos. La plantilla importa `sqlmodel` porque
  autogenerate escribe `sqlmodel.sql.sqltypes.AutoString`; en la primera migración se
  cambiaron por `sa.String`.
- **`fastapi dev` no está instalado** (necesita `fastapi[standard]`): se levanta con
  `uvicorn`.
- **Un 500 llega al navegador sin cabeceras CORS:** Starlette arma el 500 en su middleware
  más externo, por fuera de `CORSMiddleware`, así que desde otro subdominio el frontend lo ve
  como un fallo de red y no como `internal_error`. La respuesta sí tiene la forma común (se
  ve con `curl` o en el log); no confundirlo con un problema de CORS de la configuración.

## Pendiente antes de los demás modelos del dominio

Antes de modelar clientes, solicitudes y cotizaciones hay que resolver las preguntas
abiertas del modelo de datos del workspace (`docs/CONTEXTO.md`) con el agente
`arquitecto`. Las cuentas, roles y sesiones ya existen (ver "Cuentas y acceso").

## Stack

FastAPI + SQLModel + Alembic + PostgreSQL, gestor `uv`. Contraseñas con `pwdlib` (Argon2id),
JWT con PyJWT (con `crypto` para el `id_token` de Google), recuperación y estado de OAuth
con `itsdangerous`, límite con `slowapi`, correo con Jinja2 + `httpx2`.
