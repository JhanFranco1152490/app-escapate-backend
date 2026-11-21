from pathlib import Path

import pytest
from sqlmodel import func, select

from app import cli
from app.clients.models import Client
from app.suppliers.models import Supplier
from tests.factories import UserAccountFactory

TEMPLATES = Path(__file__).parents[2] / "import_templates"
CLIENT_HEADER = "client_type,first_name,last_name,document_type,document_number,phone,"
CLIENT_HEADER += "contact_source,data_consent\n"
PERSON = "person,Persona,Prueba,CC,1000000901,3100000901,whatsapp,sí\n"


@pytest.fixture
def actor(session):
    return UserAccountFactory(email="importa@example.com")


def count(session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def run(session, *args) -> int:
    return cli.main(["import-csv", *args, "--as", "importa@example.com"], session=session)


def write(tmp_path, text: str, encoding: str = "utf-8") -> str:
    path = tmp_path / "datos.csv"
    path.write_text(text, encoding=encoding)
    return str(path)


def test_the_templates_import_cleanly(session, actor, capsys):
    assert run(session, "clients", str(TEMPLATES / "clients.csv")) == 0
    assert run(session, "suppliers", str(TEMPLATES / "suppliers.csv")) == 0

    assert count(session, Client) == 3
    assert count(session, Supplier) == 2
    supplier = session.exec(
        select(Supplier).where(Supplier.trade_name == "Operador Importado")
    ).one()
    assert supplier.categories == ["ground", "tours"]


def test_bad_rows_are_reported_and_the_good_ones_saved(session, actor, tmp_path, capsys):
    bad = "person,Persona,Sin Consentimiento,CC,1000000902,3100000902,whatsapp,no\n"
    missing = "person,,Sin Nombre,CC,1000000903,,whatsapp,sí\n"
    path = write(tmp_path, CLIENT_HEADER + PERSON + bad + missing)

    assert run(session, "clients", path) == 1

    assert count(session, Client) == 1
    output = capsys.readouterr().out
    rows = [line.split()[:3] for line in output.splitlines()[1:3]]
    assert rows == [["3", "con", "errores"], ["4", "con", "errores"]]
    assert "phone: Es obligatorio." in output
    # El informe no repite los datos de la persona.
    assert "Sin Nombre" not in output and "1000000903" not in output


def test_running_it_again_skips_what_is_already_there(session, actor, tmp_path, capsys):
    path = write(tmp_path, CLIENT_HEADER + PERSON + PERSON)

    assert run(session, "clients", path) == 0
    assert run(session, "clients", path) == 0

    assert count(session, Client) == 1
    assert "omitida: 2" in capsys.readouterr().out


def test_a_dry_run_saves_nothing(session, actor, tmp_path, capsys):
    path = write(tmp_path, CLIENT_HEADER + PERSON)

    assert run(session, "clients", path, "--dry-run") == 0

    assert count(session, Client) == 0
    assert "válida: 1" in capsys.readouterr().out


def test_semicolons_and_an_excel_bom_are_understood(session, actor, tmp_path):
    text = (CLIENT_HEADER + PERSON).replace(",", ";")
    path = write(tmp_path, text, encoding="utf-8-sig")

    assert run(session, "clients", path) == 0
    assert count(session, Client) == 1


def test_an_unknown_column_stops_before_saving(session, actor, tmp_path, capsys):
    path = write(tmp_path, CLIENT_HEADER.replace("phone", "telefono") + PERSON)

    assert run(session, "clients", path) == 1

    assert count(session, Client) == 0
    assert "telefono" in capsys.readouterr().err


def test_it_needs_an_active_account(session, tmp_path, capsys):
    UserAccountFactory(email="importa@example.com", is_active=False)
    path = write(tmp_path, CLIENT_HEADER + PERSON)

    assert run(session, "clients", path) == 1
    assert count(session, Client) == 0
