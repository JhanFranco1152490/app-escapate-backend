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
  ├── common/            transversal, sin modelos de dominio:
  │   ├── errors.py      ApiError, InvalidFields (422 con `fields`), FieldError (un
  │   │                  campo con un mensaje fijo), manejadores; la llave de `fields` es
  │   │                  la ruta del campo (`attributes.max_capacity`)
  │   ├── database.py    database_conflicts: restricción de la base -> error de campo
  │   ├── columns.py     primary_key, foreign_key, timestamp, in_values (CHECK de un enum),
  │   │                  version_column y versioned (bloqueo optimista)
  │   ├── schemas.py     InputSchema (extra="forbid"), OutputSchema (from_attributes),
  │   │                  UserRef
  │   ├── fields.py      PersonName, Email, InternationalPhone, City, SearchText, RecordId,
  │   │                  validadores de texto y del número de documento
  │   │                  (valid_document_number, optional_document_number),
  │   │                  fixed_choices (lista de códigos de un enum, sin repetidos y en su
  │   │                  orden) y same_error (juntar errores en un solo ValidationError)
  │   ├── identifiers.py documento (CC, CE, PPT, PA, TI, RC, NIT con su dígito, FOREIGN) y
  │   │                  correo
  │   ├── phones.py      teléfono internacional a E.164 (phonenumbers, Colombia por defecto)
  │   ├── search.py      folded, has_every_word, starts_with, contains (sin tildes, LIKE
  │   │                  con los comodines escapados)
  │   ├── countries.py   códigos ISO 3166-1 alfa-2
  │   ├── seeding.py     seed_if_new: carga de demostración repetible (omite lo que cumple
  │   │                  una condición; same_document, la de "mismo documento")
  │   └── pagination (paginate, map_results), money, dates (today, age_on), email
  └── <dominio>/         models.py, schemas.py, services/, *_router.py, templates/email/
  tests/
  ├── conftest.py        base de prueba, sesión con rollback, app, client, csrf_client
  ├── database.py        crear/borrar la base de prueba y su protección de nombre
  ├── http.py            attach_csrf(client)
  ├── factories.py       BaseFactory (factory-boy) y las fábricas de cada dominio
  │                      (TouristServiceFactory con el rasgo `inactive`, ServiceRateFactory)
  ├── concurrency.py     wait_until_blocked(engine, n)
  ├── statements.py      recorded_statements(session): las consultas que manda un bloque
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

  | Dominio    | Puede importar de                                                       |
  | ---------- | ----------------------------------------------------------------------- |
  | `accounts` | —                                                                       |
  | `clients`  | `accounts` (`models.UserAccount`: quién registró y quién autorizó los datos) |
  | `suppliers` | `accounts` (`models.UserAccount`: quién registró y quién desactivó) |

- **Cuentas y acceso (`app/accounts/`):**
  - `UserAccount` (tabla `user_account`: `user` es palabra reservada en PostgreSQL) con un
    solo `Role`; los permisos del rol en `RolePermission`, como texto validado contra el
    registro `app/accounts/permissions.py`.
  - **Registro de permisos** (`PERMISSIONS`, código → `PermissionInfo`): `section`,
    `group` y `label` ubican el permiso en la matriz del panel (sección, fila, casilla),
    `description` es el texto completo, `requires` lista los códigos que deben ir marcados
    con él ("Gestionar" necesita "Ver") y `help` explica qué incluye, junto a su casilla.
    **Todo permiso trae su `help`** (`test_permissions.py` lo vigila); los que equivalen a
    ser administrador terminan con la advertencia "Dalo solo a quien le confiarías el rol
    Administrador.". El orden del registro es el de la matriz. Al importar el módulo se revisa que
    cada `requires` exista. Una fila de `role_permission` con un código fuera del registro no
    autoriza nada ni se muestra.
  - **Cada dominio nuevo** agrega sus códigos al registro y, en su migración, los asigna al
    rol protegido (`WHERE is_protected`, nunca por nombre) y propone los de los demás roles
    sembrados, sin dejar dos roles con el mismo conjunto no vacío. `test_seeded_roles.py`
    falla si el rol protegido no tiene todo el registro o si dos roles quedan iguales.
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
  - Documento y correo se normalizan solo con `app/common/identifiers.py` (los empleados
    aceptan CC, CE, PPT y PA) y el celular colombiano de los empleados solo con
    `app/accounts/identifiers.py`; la política de contraseñas vive solo en `app/accounts/passwords.py`. Los datos de una
    persona (nombres, apellidos, correo, documento, celular) se validan solo con `UserInput`
    de `schemas.py`, que usan la API y `create-admin`: cada tipo normaliza y valida en el
    mismo paso, con mensajes en español. El nombre completo no se guarda: `full_name` es una
    propiedad de `UserAccount`.
  - Endpoint protegido: `Depends(require_permission("dominio.accion"))`, o
    `require_any_permission(...)` si basta con uno de varios; la cuenta de la sesión, con
    `CurrentUser`. Los permisos se leen de la base en cada petición, nunca del JWT: quitar
    un permiso a un rol o cambiar el rol de alguien aplica en su siguiente petición, sin
    cerrar sus sesiones.
  - Primera cuenta (o respaldo si el único administrador pierde el acceso):
    `uv run python -m app.cli create-admin` (pide nombres, apellidos, correo, documento,
    celular y contraseña). La crea con el rol protegido, buscado por `is_protected`.
    `services/account_setup.py` (`create_account`) crea una cuenta con un rol dado, sin
    invitación por correo, y la comparten `create-admin` y la carga de demostración.
  - Datos de demostración para el entorno de pruebas compartido (staging):
    `ALLOW_DEMO_SEED=true uv run python -m app.cli seed-demo --with-demo-data`. Sin
    `ALLOW_DEMO_SEED=true` el comando se niega a correr (esa variable solo se define en
    staging, nunca en producción). Crea cuatro cuentas ficticias, una por rol sembrado
    (`demo_data.py`; las contraseñas están en el código a propósito: son cuentas inventadas
    que solo existen en staging) y, con `--with-demo-data`, unos pocos clientes, viajeros y
    proveedores ficticios, con servicios turísticos y tarifas (`demo_data.py` de `clients` y
    `suppliers`, cargados con sus servicios de alta para respetar sus validaciones). Reglas:
    - Repetible: lo que ya existe se omite y se informa, no falla ni duplica. Clientes,
      viajeros y proveedores se reconocen por su documento (`same_document`); un servicio,
      por su proveedor y su nombre, y se omite junto con sus tarifas (sus fechas son
      relativas a hoy: cargarlas otro día agregaría tarifas nuevas). Se mira antes de crear
      y no se atrapa el error del servicio, porque un viajero repetido puede fallar por
      varias reglas a la vez.
    - Los roles se buscan todos antes de crear nada (el Administrador por `is_protected`, los
      demás por nombre): si falta uno no queda una carga a medias.
    - La salida son dos tablas, nunca contraseñas: las cuentas (rol, documento, correo,
      estado) y los registros (tipo, registro, estado; el registro es el documento, o el
      nombre y el proveedor en un servicio).
    - Los datos de demostración usan al Administrador de demostración como autor.
  - Gestión de usuarios (`users_router.py`, permisos `users.view` y `users.manage`, que la
    migración asigna al rol Administrador): `services/user_queries.py` lee (lista con
    búsqueda sin tildes, ficha, ingresos) y `services/user_management.py` escribe (alta,
    edición, cambio de rol, desactivar y activar, reenviar invitación, desvincular Google).
    Reglas que no se repiten en otro lado:
    - Nunca se borra un usuario: se desactiva, lo que cierra todas sus sesiones.
    - Nadie se desactiva a sí mismo ni cambia su propio rol.
    - **Siempre queda al menos una persona activa cuyo rol tenga `users.manage`**: vive solo
      en `services/manager_guard.py` (`ensure_user_managers_remain`) y la usan desactivar,
      cambiar el rol de alguien y quitarle `users.manage` a un rol. Bloquea las filas de los
      gestores en orden de `id`, así que se llama **antes** de bloquear cualquier otra
      cuenta: dos cambios simultáneos se esperan y no se bloquean entre sí.
    - Cambiar el rol (`PUT /api/users/{id}/role`) no cierra sesiones. Si el cambio da o
      quita el rol protegido y la persona está activa, después del `commit()` le llega el
      correo `role_changed`; si falla, el cambio queda hecho.
    - El correo con la invitación se envía después del `commit()`; si falla, la cuenta
      queda creada y la respuesta trae `invitation_sent: false`.
    - Las restricciones únicas de la base (correo, documento, celular) se traducen al mismo
      error de campo repetido por el nombre de la restricción, nunca por su mensaje, que
      trae el valor.
    - La búsqueda usa la extensión `unaccent` de PostgreSQL (la crea la migración).
  - Roles (`roles_router.py`, permisos `roles.view` y `roles.manage`):
    `services/role_queries.py` lee (lista con número de personas, detalle, catálogo de
    permisos) y `services/role_management.py` escribe (crear, editar, borrar). Reglas que no
    se repiten en otro lado:
    - El rol protegido (`is_protected`, hoy Administrador) no se renombra, no se borra y
      siempre tiene todos los permisos; solo se edita su descripción. Se reconoce por
      `is_protected`, nunca por nombre.
    - Sin roles repetidos: el nombre es único sin distinguir mayúsculas (índice
      `uq_role_name_lower`) y dos roles no tienen el mismo conjunto de permisos, salvo el
      vacío. Solo se revisa cuando cambian los permisos.
    - Nadie cambia los permisos de su propio rol. Un rol con personas, activas o inactivas,
      no se borra.
    - Crear, editar y borrar roles, y cambiar el rol de alguien, toman primero
      `lock_role_writes(session)` (`pg_advisory_xact_lock` con una llave fija): la base no
      puede comparar conjuntos de filas, y sin el bloqueo dos altas simultáneas iguales
      pasarían las dos. Lo que esas operaciones revisan se lee después del bloqueo.
    - Toda escritura de `role_management` va dentro de `_database_conflicts`, no solo el
      `commit()`: un `flush()` automático también puede chocar con un índice único.
    - `GET /api/roles` acepta `users.view` o `roles.view`; `GET /api/roles/{id}` y
      `GET /api/permissions`, `roles.view` o `users.manage` (la pantalla de cambiar rol los
      necesita).
  - Crear una contraseña desde un enlace (recuperación, 30 min; invitación, 72 h):
    `services/reset_tokens.py` firma el token sin guardarlo (deja de valer al cambiar la
    contraseña o el correo) y `services/password_reset.py` lo usa. Los correos que salen
    después de responder van como `PendingEmail` en `BackgroundTasks`: nunca se pasa la
    sesión de base de datos de la petición a una tarea en segundo plano. Otros dominios
    invitan a alguien con `password_reset.send_invitation(user)`.
  - El bloqueo por intentos vive solo en `services/lockout.py`.
- **Clientes y viajeros (`app/clients/`):** el CRM: clientes (`Client`) y las personas que
  viajan (`Traveler`). Permisos `clients.view`, `clients.manage`, `travelers.view` y
  `travelers.manage`; la migración da los cuatro al rol protegido y al Asesor comercial, y
  los de "Ver" al Operativo. `services/client_queries.py` y `services/traveler_queries.py`
  leen (lista con búsqueda sin tildes y ficha), `services/client_management.py` y
  `services/traveler_management.py` escriben (alta y edición), y los routers son
  `clients_router.py` (`/api/clients`) y `travelers_router.py` (`/api/travelers`). Reglas que
  no se repiten en otro lado:
  - Un cliente es una persona (nombres y apellidos; CC, CE, PPT o PA) o una empresa (razón
    social; NIT con dígito de verificación). Qué campos aplican a cada tipo lo validan
    `ClientInput` (cada error en su campo) y los `CHECK` de la tabla. El tipo no se edita.
  - El documento del cliente es **opcional** pero no se repite (índice único parcial
    `uq_client_document`); teléfono y correo sí se pueden repetir. El teléfono se guarda en
    E.164 con `app/common/phones.py` (`phonenumbers`, Colombia por defecto) y se busca por
    cualquier parte desde 3 dígitos.
  - El viajero es un registro propio: su cliente de referencia es opcional, y "es el mismo
    cliente" (`is_the_client`, solo para una persona y una vez por cliente) no copia ni
    sincroniza datos. Su documento es obligatorio y único; la edad y si es menor de edad se
    calculan con la fecha de Bogotá.
  - La autorización de tratamiento de datos se registra al crear (quién y cuándo) y la
    edición no la cambia.
  - Nunca se borra un cliente ni un viajero (`ON DELETE RESTRICT`).
  - **Bloqueo optimista:** `version` es el `version_id_col` de los dos modelos. El PUT trae
    `expected_version`: si no coincide con la leída responde `StaleVersion`, y si otra
    petición guarda entre esa revisión y el commit, el `StaleDataError` también sale como
    `409 stale_version`.
  - Las listas no traen notas ni observaciones: pueden tener datos sensibles.
- **Proveedores (`app/suppliers/`):** los proveedores turísticos (`Supplier`). Permisos
  `suppliers.view` y `suppliers.manage`; la migración da los dos al rol protegido y al
  Encargado de proveedores, y "Ver" al Asesor comercial y al Operativo.
  `services/supplier_queries.py` lee (lista con búsqueda y filtros, y ficha),
  `services/supplier_management.py` escribe (alta, edición, desactivar y activar) y el
  router es `suppliers_router.py` (`/api/suppliers`). Reglas que no se repiten en otro lado:
  - La clasificación es una o varias categorías de `SupplierCategory`, guardadas en un
    arreglo de PostgreSQL (`categories`, con el `ARRAY` de `sqlalchemy.dialects.postgresql`:
    el genérico no sabe filtrar con `@>`). Se devuelven sin repetidos y en el orden del enum,
    que es la misma lista de tipos de servicio de la oferta.
  - El documento es **opcional** pero no se repite (`uq_supplier_document`): NIT, CC, CE o
    `FOREIGN` (identificación tributaria de otro país, que pierde el guion como los demás).
  - Un solo contacto, con **teléfono o correo, al menos uno**: un `model_validator(mode=
    "wrap")` pone el error en los dos campos junto con los demás errores del cuerpo (un
    validador de campo no ve los campos que vienen después). Vacío o solo espacios cuenta
    como no llenado.
  - No se borra: se desactiva y se activa (`POST …/deactivate` y `…/activate`), guardando
    quién y cuándo, y las dos exigen `expected_version`. Repetir la acción no cambia nada.
    Al desactivar se asigna la relación `deactivated_by`, no el id: la ficha ya la trae
    cargada y al guardar pisaría el id.
  - La comisión es solo de referencia (`numeric(5,2)`, viaja como texto `"10.00"`) y
    `agreement_expired` se calcula con la fecha de Bogotá; ninguno de los dos desactiva
    nada.
  - La lista no trae notas, condiciones de pago ni comisión, y sí `active_service_count`
    (servicios activos, con una subconsulta: el número de consultas no crece con las filas).
  - **Servicios turísticos y tarifas** (`TouristService` y `ServiceRate`, en
    `tourist_service_models.py`, aparte de `models.py` para evitar un import circular con
    `service_types.py`). Viven en este dominio y no en uno propio porque la lista de
    proveedores cuenta servicios: en dos dominios sería un ciclo. Permisos
    `tourist_services.view` (requiere `suppliers.view`) y `tourist_services.manage`; la
    migración da los dos al rol protegido y al Encargado de proveedores, y "Ver" al Asesor
    comercial y al Operativo. Las tarifas no tienen permiso propio. Las listas fijas (tipos,
    monedas, unidades de cobro y opciones de cada tipo) viven solo en `service_types.py`; los
    campos de cada tipo, en `service_attributes.py`; los esquemas, en
    `tourist_service_schemas.py` y `rate_schemas.py`; lee y escribe
    `services/tourist_service_queries.py`, `tourist_service_management.py`,
    `rate_queries.py` y `rate_management.py`, y el router es `tourist_services_router.py`
    (`/api/suppliers/{id}/tourist-services` y `/api/tourist-services/...`). Reglas que no se
    repiten en otro lado:
    - El tipo del servicio es una de las clasificaciones del proveedor (`ServiceType =
      SupplierCategory`, el mismo enum). Solo se revisa al crear: quitarle la clasificación
      al proveedor después no toca sus servicios.
    - Proveedor y tipo no cambian después de crear (cambiar el tipo en un `PUT` es un error
      en `service_type`). Un proveedor inactivo no recibe servicios nuevos ni se le activa
      uno (`409 supplier_inactive`), pero sus servicios se editan.
    - Los campos propios de cada tipo van en `attributes` (`jsonb`; la base solo exige que sea
      un objeto). Se validan con el modelo de su `service_type` (`ATTRIBUTE_MODELS`) dentro
      de un `model_validator(mode="wrap")`, no con una unión discriminada del cuerpo, que
      metería el tipo en la ruta del error: así cada error sale como
      `attributes.<campo>`, junto con los del resto del cuerpo. Se guarda siempre
      `stored_attributes(...)` (validado y sin los opcionales vacíos), y la columna se
      reemplaza entera al editar, nunca se modifica en su lugar. El OpenAPI muestra
      `attributes` como la unión de los ocho modelos.
    - Un servicio no se borra: se desactiva y se activa como un proveedor. Un servicio
      inactivo no recibe tarifas nuevas (`409 service_inactive`), pero las que tiene se
      editan y se borran. Las tarifas sí se borran (`DELETE` con `expected_version` en la
      query): lo que las use después copia su valor.
    - Una tarifa está en COP o USD, en la moneda del proveedor y **sin conversión**. COP en
      pesos enteros y USD con centavos, los dos en `numeric(14,2)` (un `CHECK` impide
      centavos en COP), y `amount` viaja como texto con los decimales de su moneda
      (`"710000"`, `"1250.50"`).
    - La unidad de cobro sale de `CHARGE_UNITS[tipo]` y se revisa en el servicio de tarifas,
      que es donde se conoce el tipo (error en `charge_unit`). Las vigencias se pueden
      superponer; el estado (`upcoming`, `current`, `expired`) se calcula con la fecha de
      Bogotá (`validity_status`), y la lista va vigentes, próximas y vencidas.
    - Crear un servicio y activarlo bloquean la fila del proveedor (`FOR UPDATE`), y crear
      una tarifa la del servicio, para que una desactivación simultánea no deje algo nuevo
      colgando de un registro inactivo.
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
  La llave de `fields` es la ruta del campo sin `body`/`query`/`path` ni índices de lista
  (`name`, `categories`, `attributes.max_capacity`).
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
  `app/common/money.py` (`round_to_peso`, `apply_percentage`). **Única excepción:** las
  tarifas en dólares de los servicios turísticos (`service_rate.amount`, `numeric(14,2)`)
  guardan centavos y viajan como texto decimal; en COP siguen siendo pesos enteros. Pasar
  un valor en USD a COP es una conversión que hace quien la necesite (la cotización), con
  `money.py`.
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
  sembrados (`administrator_role` buscado por `is_protected`), y `helpers.py` trae los datos
  de una persona nueva (`NEW_USER`), `second_client(app)` para simular otro navegador y
  `signed_in(app, session, user)` para abrir en él la sesión de una persona.
  En `tests/suppliers/`, `samples.py` trae atributos válidos de cada tipo de servicio.
  `wait_until_blocked(engine, n)` (`tests/concurrency.py`) espera a que las transacciones de
  una prueba de concurrencia queden detenidas en un bloqueo. Un servicio que pagina
  se prueba con `fake_request()` de `tests/http.py`.
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
- **Los mensajes de error de PostgreSQL salen en el idioma del servidor:** para saber qué
  restricción falló se usa `diag.constraint_name` (`app/common/database.py`), nunca el texto
  del mensaje. Las pruebas de restricciones comparan ese nombre.
- **`session.get` con un objeto ya en la sesión y vencido** lo refresca y carga sus
  relaciones con consultas aparte, aunque se le pasen `joinedload`. Una prueba de "una sola
  consulta" simula una petición nueva vaciando la sesión (`session.expunge_all()`).
- **`fastapi dev` no está instalado** (necesita `fastapi[standard]`): se levanta con
  `uvicorn`.
- **Un 500 llega al navegador sin cabeceras CORS:** Starlette arma el 500 en su middleware
  más externo, por fuera de `CORSMiddleware`, así que desde otro subdominio el frontend lo ve
  como un fallo de red y no como `internal_error`. La respuesta sí tiene la forma común (se
  ve con `curl` o en el log); no confundirlo con un problema de CORS de la configuración.

## Pendiente antes de los demás modelos del dominio

Antes de modelar solicitudes, cotizaciones y ventas hay que resolver las preguntas abiertas
del modelo de datos del workspace (`docs/CONTEXTO.md`) con el agente `arquitecto`. Ya
existen las cuentas, roles y sesiones ("Cuentas y acceso"), los clientes y viajeros
("Clientes y viajeros") y los proveedores con sus servicios turísticos y tarifas
("Proveedores").

## Stack

FastAPI + SQLModel + Alembic + PostgreSQL, gestor `uv`. Contraseñas con `pwdlib` (Argon2id),
JWT con PyJWT (con `crypto` para el `id_token` de Google), recuperación y estado de OAuth
con `itsdangerous`, límite con `slowapi`, correo con Jinja2 + `httpx2`, teléfonos internacionales con
`phonenumbers`.
