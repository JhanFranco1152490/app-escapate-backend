"""Comandos de administración.

uv run python -m app.cli create-admin
uv run python -m app.cli seed-demo [--with-demo-data]
uv run python -m app.cli import-csv {clients,suppliers} ARCHIVO --as CORREO [--dry-run]
"""

import argparse
import getpass
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from sqlmodel import Session, select

from app.accounts.models import UserAccount
from app.accounts.services.account_setup import SetupError
from app.accounts.services.admin_setup import create_admin
from app.accounts.services.demo_accounts import SeededAccount, seed_demo_accounts
from app.clients.services.demo_clients import seed_demo_clients
from app.common.identifiers import normalize_email
from app.common.seeding import SeededRecord
from app.core.config import settings
from app.core.db import engine
from app.finance.demo_finance import seed_demo_finance
from app.imports.csv_rows import CsvFormatError, read_rows
from app.imports.importer import IMPORT_KINDS, RowStatus, import_rows
from app.quotes.services.demo_quotes import seed_demo_packages, seed_demo_quotes
from app.sales.demo_sales import seed_demo_sales
from app.suppliers.services.demo_suppliers import seed_demo_suppliers
from app.suppliers.services.demo_tourist_services import seed_demo_tourist_services
from app.travel_requests.services.demo_request_travelers import seed_demo_request_travelers
from app.travel_requests.services.demo_travel_requests import seed_demo_travel_requests


def _create_admin(session: Session, args: argparse.Namespace) -> int:
    first_name = input("Nombres: ")
    last_name = input("Apellidos: ")
    email = input("Correo (Gmail personal): ")
    document_type = input("Tipo de documento (CC, CE, PPT, PA): ")
    document_number = input("Número de documento: ")
    phone = input("Celular (10 dígitos): ")
    password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if getpass.getpass("Repite la contraseña: ") != password:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    try:
        user = create_admin(
            session,
            first_name=first_name,
            last_name=last_name,
            email=email,
            document_type=document_type,
            document_number=document_number,
            phone=phone,
            password=password,
        )
    except SetupError as error:
        for message in error.messages:
            print(message, file=sys.stderr)
        return 1
    print(f"Administrador creado (id {user.id}).")
    return 0


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows, strict=True)]
    for line in (headers, *rows):
        cells = (cell.ljust(width) for cell, width in zip(line, widths, strict=True))
        print("  ".join(cells).rstrip())


def _status(created: bool, feminine: bool = False) -> str:
    if created:
        return "creada" if feminine else "creado"
    return "omitida" if feminine else "omitido"


def _print_accounts(accounts: Sequence[SeededAccount]) -> None:
    rows = [
        [
            account.user.role.name,
            f"{account.user.document_type} {account.user.document_number}",
            account.user.email,
            _status(account.created, feminine=True),
        ]
        for account in accounts
    ]
    _print_table(["Rol", "Documento", "Correo", "Estado"], rows)


def _print_records(records: Sequence[SeededRecord]) -> None:
    rows = [[record.kind, record.label, _status(record.created)] for record in records]
    _print_table(["Tipo", "Registro", "Estado"], rows)


def _seed_demo(session: Session, args: argparse.Namespace) -> int:
    if not settings.allow_demo_seed:
        print(
            "seed-demo solo corre con ALLOW_DEMO_SEED=true, que se define únicamente en el "
            "entorno de pruebas compartido.",
            file=sys.stderr,
        )
        return 1
    try:
        accounts = seed_demo_accounts(session)
    except SetupError as error:
        for message in error.messages:
            print(message, file=sys.stderr)
        return 1
    _print_accounts(accounts)
    if args.with_demo_data:
        # La primera cuenta de demostración es la del administrador.
        actor = accounts[0].user
        print()
        # Cada carga después de la que le da sus referencias: los servicios buscan a su
        # proveedor, y las solicitudes a su cliente, por el documento; los viajeros de las
        # solicitudes, a la solicitud y al viajero; las cotizaciones, a la solicitud y al
        # paquete; las ventas, a la cotización aceptada; los costos reales, a la venta.
        _print_records(
            [
                *seed_demo_clients(session, actor),
                *seed_demo_suppliers(session, actor),
                *seed_demo_tourist_services(session, actor),
                *seed_demo_travel_requests(session, actor),
                *seed_demo_request_travelers(session, actor),
                *seed_demo_packages(session, actor),
                *seed_demo_quotes(session, actor),
                *seed_demo_sales(session, actor),
                *seed_demo_finance(session, actor),
            ]
        )
    return 0


def _import_csv(session: Session, args: argparse.Namespace) -> int:
    actor = session.exec(
        select(UserAccount).where(UserAccount.email == normalize_email(args.actor_email))
    ).first()
    if actor is None or not actor.is_active:
        print("No hay una cuenta activa con ese correo.", file=sys.stderr)
        return 1
    kind = IMPORT_KINDS[args.kind]
    path = Path(args.file)
    if not path.is_file():
        print(f"No existe el archivo {path}.", file=sys.stderr)
        return 1
    try:
        rows = list(read_rows(path, kind.columns, kind.list_columns, kind.bool_columns))
    except (CsvFormatError, UnicodeDecodeError) as error:
        detail = "Guárdalo como CSV UTF-8." if isinstance(error, UnicodeDecodeError) else error
        print(f"No se pudo leer el archivo. {detail}", file=sys.stderr)
        return 1
    results = import_rows(session, actor, kind, rows, dry_run=args.dry_run)
    lines = [
        [str(result.number), result.status.value, " ".join(result.messages)]
        for result in results
        if result.status != RowStatus.CREATED
    ]
    if lines:
        _print_table(["Fila", "Estado", "Detalle"], lines)
        print()
    totals = Counter(result.status for result in results)
    print(", ".join(f"{status.value}: {totals[status]}" for status in RowStatus))
    if args.dry_run:
        print("Prueba sin guardar: no se creó nada.")
    return 1 if totals[RowStatus.INVALID] else 0


_COMMANDS = {
    "create-admin": _create_admin,
    "seed-demo": _seed_demo,
    "import-csv": _import_csv,
}


def main(argv: list[str] | None = None, session: Session | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin", help="crea un administrador")
    seed_demo = commands.add_parser("seed-demo", help="carga datos de demostración (staging)")
    seed_demo.add_argument(
        "--with-demo-data",
        action="store_true",
        help="agrega clientes, proveedores, solicitudes, cotizaciones y ventas ficticios",
    )
    import_csv = commands.add_parser(
        "import-csv", help="carga inicial de clientes o proveedores desde un CSV"
    )
    import_csv.add_argument("kind", choices=sorted(IMPORT_KINDS))
    import_csv.add_argument("file", help="CSV con una columna por campo (ver import_templates/)")
    import_csv.add_argument(
        "--as",
        dest="actor_email",
        required=True,
        help="correo de la cuenta que figura como quien registró los datos",
    )
    import_csv.add_argument(
        "--dry-run", action="store_true", help="solo valida el archivo, no guarda nada"
    )
    args = parser.parse_args(argv)
    command = _COMMANDS[args.command]
    if session is not None:
        return command(session, args)
    with Session(engine) as own_session:
        return command(own_session, args)


if __name__ == "__main__":
    sys.exit(main())
