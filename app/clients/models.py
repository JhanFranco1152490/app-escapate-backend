from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Index, Integer, String, Text, func, text
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.columns import foreign_key, in_values, primary_key, timestamp
from app.common.dates import age_on, today

ADULT_AGE = 18


class ClientType(StrEnum):
    PERSON = "person"
    COMPANY = "company"


class ClientDocumentType(StrEnum):
    CC = "CC"
    CE = "CE"
    PPT = "PPT"
    PA = "PA"
    NIT = "NIT"


# El NIT es de las empresas; una persona natural se registra con su documento de identidad.
PERSON_DOCUMENT_TYPES = (
    ClientDocumentType.CC,
    ClientDocumentType.CE,
    ClientDocumentType.PPT,
    ClientDocumentType.PA,
)


class TravelerDocumentType(StrEnum):
    CC = "CC"
    CE = "CE"
    PPT = "PPT"
    PA = "PA"
    TI = "TI"
    RC = "RC"


class ContactSource(StrEnum):
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    WHATSAPP = "whatsapp"
    GOOGLE = "google"
    REFERRAL = "referral"
    WALK_IN = "walk_in"
    OTHER = "other"


def _version():
    return Field(default=None, sa_column=Column(Integer, nullable=False))


def _versioned(cls) -> dict:
    # Bloqueo optimista: cada UPDATE exige que la versión en la base siga siendo la que se
    # leyó, y la sube en uno. Si otra petición guardó antes, SQLAlchemy lanza StaleDataError.
    return {"version_id_col": cls.__table__.c.version}


_PERSON_DOCUMENTS = ", ".join(f"'{member.value}'" for member in PERSON_DOCUMENT_TYPES)


class Client(SQLModel, table=True):
    __tablename__ = "client"
    __table_args__ = (
        CheckConstraint(in_values("client_type", ClientType), name="ck_client_client_type"),
        CheckConstraint(
            in_values("document_type", ClientDocumentType), name="ck_client_document_type"
        ),
        CheckConstraint(
            "(document_type IS NULL) = (document_number IS NULL)", name="ck_client_document_pair"
        ),
        CheckConstraint(
            "client_type <> 'person' OR (first_name IS NOT NULL AND last_name IS NOT NULL "
            "AND business_name IS NULL "
            f"AND (document_type IS NULL OR document_type IN ({_PERSON_DOCUMENTS})))",
            name="ck_client_person",
        ),
        CheckConstraint(
            "client_type <> 'company' OR (business_name IS NOT NULL AND first_name IS NULL "
            "AND last_name IS NULL AND birth_date IS NULL "
            "AND (document_type IS NULL OR document_type = 'NIT'))",
            name="ck_client_company",
        ),
        CheckConstraint(
            in_values("contact_source", ContactSource), name="ck_client_contact_source"
        ),
        CheckConstraint(
            "contact_source <> 'other' OR contact_source_detail IS NOT NULL",
            name="ck_client_contact_source_detail",
        ),
        # El documento es opcional: solo se repite la pareja cuando sí se registró.
        Index(
            "uq_client_document",
            "document_type",
            "document_number",
            unique=True,
            postgresql_where=text("document_number IS NOT NULL"),
        ),
    )

    id: int | None = primary_key()
    client_type: str = Field(max_length=10)
    first_name: str | None = Field(default=None, max_length=75)
    last_name: str | None = Field(default=None, max_length=75)
    business_name: str | None = Field(default=None, max_length=150)
    document_type: str | None = Field(default=None, max_length=3)
    document_number: str | None = Field(default=None, max_length=30)
    birth_date: date | None = None
    # E.164: "+" y hasta 15 dígitos.
    phone: str = Field(max_length=16)
    email: str | None = Field(default=None, max_length=254)
    city: str | None = Field(default=None, max_length=80)
    contact_source: str = Field(max_length=20)
    contact_source_detail: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    data_consent_at: datetime | None = timestamp()
    data_consent_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = _version()

    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Client.created_by_id]"}
    )
    data_consent_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Client.data_consent_by_id]"}
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return _versioned(cls)

    @property
    def display_name(self) -> str:
        if self.client_type == ClientType.COMPANY:
            return self.business_name
        return f"{self.first_name} {self.last_name}"


class Traveler(SQLModel, table=True):
    __tablename__ = "traveler"
    __table_args__ = (
        CheckConstraint(
            in_values("document_type", TravelerDocumentType), name="ck_traveler_document_type"
        ),
        CheckConstraint(
            "NOT is_the_client OR reference_client_id IS NOT NULL",
            name="ck_traveler_is_the_client",
        ),
        Index("uq_traveler_document", "document_type", "document_number", unique=True),
        # Un cliente tiene a lo sumo una ficha de viajero propia.
        Index(
            "uq_traveler_is_the_client",
            "reference_client_id",
            unique=True,
            postgresql_where=text("is_the_client"),
        ),
    )

    id: int | None = primary_key()
    first_name: str = Field(max_length=75)
    last_name: str = Field(max_length=75)
    document_type: str = Field(max_length=3)
    document_number: str = Field(max_length=30)
    birth_date: date
    # Código ISO 3166-1 alfa-2.
    nationality: str = Field(sa_column=Column(String(2), nullable=False))
    reference_client_id: int | None = foreign_key(
        "client.id", ondelete="RESTRICT", nullable=True, index=True
    )
    is_the_client: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    data_consent_at: datetime | None = timestamp()
    data_consent_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = _version()

    reference_client: Client | None = Relationship()
    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Traveler.created_by_id]"}
    )
    data_consent_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Traveler.data_consent_by_id]"}
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return _versioned(cls)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        return age_on(self.birth_date, today())

    @property
    def is_minor(self) -> bool:
        return self.age < ADULT_AGE
