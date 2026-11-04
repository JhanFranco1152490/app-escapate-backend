from sqlmodel import select

from app.suppliers.demo_data import DEMO_SUPPLIERS
from app.suppliers.models import Supplier
from app.suppliers.services.demo_suppliers import seed_demo_suppliers
from tests.factories import UserAccountFactory


def test_it_loads_the_demo_suppliers_as_active(session):
    actor = UserAccountFactory()

    records = seed_demo_suppliers(session, actor)

    suppliers = session.exec(select(Supplier)).all()
    assert len(suppliers) == len(DEMO_SUPPLIERS)
    assert all(supplier.is_active and supplier.created_by_id == actor.id for supplier in suppliers)
    assert all(record.created for record in records)


def test_loading_it_again_skips_every_record(session):
    actor = UserAccountFactory()
    seed_demo_suppliers(session, actor)

    records = seed_demo_suppliers(session, actor)

    assert not any(record.created for record in records)
    assert len(session.exec(select(Supplier)).all()) == len(DEMO_SUPPLIERS)


def test_the_demo_suppliers_cover_more_than_one_category(session):
    seed_demo_suppliers(session, UserAccountFactory())

    suppliers = session.exec(select(Supplier)).all()
    categories = {category for supplier in suppliers for category in supplier.categories}

    assert len(categories) > 1
