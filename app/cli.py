"""Comandos de administración.

uv run python -m app.cli create-admin
uv run python -m app.cli seed-demo [--with-demo-data]
"""

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlmodel import Session

from app.accounts.services.account_setup import SetupError
from app.accounts.services.admin_setup import create_admin
from app.accounts.services.demo_accounts import SeededAccount, seed_demo_accounts
from app.clients.services.demo_clients import seed_demo_clients
from app.common.seeding import SeededRecord
from app.core.config import settings
from app.core.db import engine
from app.suppliers.services.demo_suppliers import seed_demo_suppliers


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
    rows = [[record.kind, record.document, _status(record.created)] for record in records]
    _print_table(["Tipo", "Documento", "Estado"], rows)


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
        _print_records([*seed_demo_clients(session, actor), *seed_demo_suppliers(session, actor)])
    return 0


_COMMANDS = {"create-admin": _create_admin, "seed-demo": _seed_demo}


def main(argv: list[str] | None = None, session: Session | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin", help="crea un administrador")
    seed_demo = commands.add_parser("seed-demo", help="carga datos de demostración (staging)")
    seed_demo.add_argument(
        "--with-demo-data",
        action="store_true",
        help="agrega clientes, viajeros y proveedores ficticios",
    )
    args = parser.parse_args(argv)
    command = _COMMANDS[args.command]
    if session is not None:
        return command(session, args)
    with Session(engine) as own_session:
        return command(own_session, args)


if __name__ == "__main__":
    sys.exit(main())
