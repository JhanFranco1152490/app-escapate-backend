"""Comandos de administración.

uv run python -m app.cli create-admin
"""

import argparse
import getpass
import sys

from sqlmodel import Session

from app.accounts.services.admin_setup import SetupError, create_admin
from app.core.db import engine


def _create_admin(session: Session) -> int:
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


def main(argv: list[str] | None = None, session: Session | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["create-admin"])
    parser.parse_args(argv)
    if session is not None:
        return _create_admin(session)
    with Session(engine) as own_session:
        return _create_admin(own_session)


if __name__ == "__main__":
    sys.exit(main())
