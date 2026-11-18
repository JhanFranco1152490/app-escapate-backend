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
uv run python -m app.cli create-admin   # primera cuenta, con el rol Administrador (protegido)
uv run uvicorn app.main:app --reload
```

`create-admin` pide nombres, apellidos, correo (Gmail personal), tipo y número de documento,
celular colombiano de 10 dígitos y contraseña. Las demás personas las registra el
administrador desde la gestión de usuarios (`/api/users`), y a cada una le llega un correo
para crear su propia contraseña. Los roles y lo que autoriza cada uno se gestionan en
`/api/roles` y `/api/permissions`.

Los clientes (personas o empresas) y los viajeros se gestionan en `/api/clients` y
`/api/travelers`. El rol Asesor comercial puede verlos y modificarlos, y el Operativo solo
verlos.

Los proveedores turísticos se gestionan en `/api/suppliers`. El Encargado de proveedores
puede registrarlos, editarlos, desactivarlos y activarlos; el Asesor comercial y el
Operativo solo verlos.

Los servicios turísticos de cada proveedor se gestionan en
`/api/suppliers/{id}/tourist-services` y `/api/tourist-services`, junto con sus tarifas
(en COP o USD, sin conversión). El Encargado de proveedores puede registrarlos, editarlos,
desactivarlos y gestionar sus tarifas; el Asesor comercial y el Operativo solo verlos.

Las solicitudes de viaje de los clientes se gestionan en `/api/travel-requests` (con
`?status=pending&sort=oldest`, las que esperan cotización, de la más antigua a la más
reciente). El Asesor comercial puede registrarlas, editarlas, reasignarlas, cerrarlas y
reabrirlas; el Operativo solo verlas.

Con `EMAIL_BACKEND=console` (el valor local) los correos no se envían: se imprimen en la
terminal del backend, con el enlace de recuperación o de invitación listo para copiar.

La búsqueda de usuarios, clientes, viajeros, proveedores y solicitudes y el orden de los roles sin tildes usan la extensión `unaccent` de
PostgreSQL. La migración la crea; desde PostgreSQL 13 es una extensión confiable, así que
basta con que el rol sea dueño de la base (no hace falta superusuario).

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
