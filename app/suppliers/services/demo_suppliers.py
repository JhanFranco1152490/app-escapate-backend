"""Carga de proveedores de demostración. Repetible: un documento ya registrado se omite."""

from functools import partial

from sqlmodel import Session

from app.accounts.models import UserAccount
from app.common.seeding import SeededRecord, same_document, seed_if_new
from app.suppliers.demo_data import DEMO_SUPPLIERS
from app.suppliers.models import Supplier
from app.suppliers.schemas import SupplierCreate
from app.suppliers.services.supplier_management import create_supplier


def seed_demo_suppliers(session: Session, actor: UserAccount) -> list[SeededRecord]:
    return [
        seed_if_new(
            session,
            Supplier,
            "Proveedor",
            f"{data['document_type']} {data['document_number']}",
            same_document(Supplier, data["document_type"], data["document_number"]),
            partial(create_supplier, session, actor, SupplierCreate(**data)),
        )
        for data in DEMO_SUPPLIERS
    ]
