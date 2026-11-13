from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Column, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.clients.models import Client
from app.common.columns import (
    foreign_key,
    in_values,
    primary_key,
    timestamp,
    version_column,
    versioned,
)

CODE_PREFIX = "SOL-"


class TravelRequestStatus(StrEnum):
    NEW = "new"
    QUOTING = "quoting"
    QUOTED = "quoted"
    CLOSED = "closed"


# Las que todavía esperan una cotización.
PENDING_STATUSES = (TravelRequestStatus.NEW, TravelRequestStatus.QUOTING)


class DateMode(StrEnum):
    EXACT = "exact"
    FLEXIBLE = "flexible"


class TripType(StrEnum):
    LEISURE = "leisure"
    FAMILY = "family"
    HONEYMOON = "honeymoon"
    CORPORATE = "corporate"
    GROUP = "group"
    ADVENTURE = "adventure"
    OTHER = "other"


class AccommodationCategory(StrEnum):
    BUDGET = "budget"
    THREE_STAR = "three_star"
    FOUR_STAR = "four_star"
    FIVE_STAR = "five_star"


class CloseReason(StrEnum):
    CLIENT_DECLINED = "client_declined"
    NO_RESPONSE = "no_response"
    BOUGHT_ELSEWHERE = "bought_elsewhere"
    DUPLICATE = "duplicate"
    OTHER = "other"


def format_code(request_id: int) -> str:
    return f"{CODE_PREFIX}{request_id:04d}"


_TRIP_TYPES = ", ".join(f"'{member.value}'" for member in TripType)


class TravelRequest(SQLModel, table=True):
    __tablename__ = "travel_request"
    __table_args__ = (
        CheckConstraint(in_values("date_mode", DateMode), name="ck_travel_request_date_mode"),
        CheckConstraint(
            "date_mode <> 'exact' OR (departure_date IS NOT NULL "
            "AND (return_date IS NULL OR return_date >= departure_date) "
            "AND window_start IS NULL AND window_end IS NULL AND approx_nights IS NULL)",
            name="ck_travel_request_exact_dates",
        ),
        CheckConstraint(
            "date_mode <> 'flexible' OR (window_start IS NOT NULL AND window_end IS NOT NULL "
            "AND window_end >= window_start "
            "AND departure_date IS NULL AND return_date IS NULL)",
            name="ck_travel_request_flexible_dates",
        ),
        CheckConstraint("approx_nights BETWEEN 1 AND 365", name="ck_travel_request_approx_nights"),
        CheckConstraint("adults BETWEEN 1 AND 99", name="ck_travel_request_adults"),
        CheckConstraint("minors BETWEEN 0 AND 99", name="ck_travel_request_minors"),
        CheckConstraint(
            "(budget_min IS NULL OR budget_min > 0) AND (budget_max IS NULL OR budget_max > 0) "
            "AND (budget_min IS NULL OR budget_max IS NULL OR budget_max >= budget_min)",
            name="ck_travel_request_budget",
        ),
        CheckConstraint(
            f"trip_types <@ ARRAY[{_TRIP_TYPES}]::varchar[]", name="ck_travel_request_trip_types"
        ),
        CheckConstraint(
            in_values("accommodation_category", AccommodationCategory),
            name="ck_travel_request_accommodation_category",
        ),
        CheckConstraint(in_values("status", TravelRequestStatus), name="ck_travel_request_status"),
        CheckConstraint(
            in_values("close_reason", CloseReason), name="ck_travel_request_close_reason"
        ),
        # Una solicitud cerrada siempre dice por qué, quién y cuándo; una abierta, nada de eso.
        CheckConstraint(
            "(status = 'closed') = (close_reason IS NOT NULL) "
            "AND (status = 'closed') = (closed_by_id IS NOT NULL) "
            "AND (status = 'closed') = (closed_at IS NOT NULL)",
            name="ck_travel_request_closed",
        ),
        CheckConstraint(
            "close_reason IS DISTINCT FROM 'other' OR close_note IS NOT NULL",
            name="ck_travel_request_close_note",
        ),
    )

    id: int | None = primary_key()
    client_id: int = foreign_key("client.id", ondelete="RESTRICT", index=True)
    destination: str = Field(max_length=150)
    origin: str | None = Field(default=None, max_length=120)
    date_mode: str = Field(max_length=10)
    departure_date: date | None = None
    return_date: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    approx_nights: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    adults: int = Field(sa_column=Column(SmallInteger, nullable=False))
    minors: int = Field(sa_column=Column(SmallInteger, nullable=False))
    # Pesos colombianos enteros: es la referencia de lo que el cliente quiere gastar.
    budget_min: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    budget_max: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    trip_types: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String(20)), nullable=False, server_default="{}"),
    )
    accommodation_category: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(default=TravelRequestStatus.NEW, max_length=10, index=True)
    assigned_to_id: int = foreign_key("user_account.id", ondelete="RESTRICT", index=True)
    close_reason: str | None = Field(default=None, max_length=20)
    close_note: str | None = Field(default=None, max_length=300)
    closed_by_id: int | None = foreign_key("user_account.id", ondelete="RESTRICT", nullable=True)
    closed_at: datetime | None = timestamp(nullable=True)
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()
    updated_at: datetime | None = timestamp(onupdate=func.now())
    version: int | None = version_column()

    client: Client = Relationship()
    assigned_to: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[TravelRequest.assigned_to_id]"}
    )
    closed_by: UserAccount | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[TravelRequest.closed_by_id]"}
    )
    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[TravelRequest.created_by_id]"}
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return versioned(cls)

    @property
    def code(self) -> str:
        return format_code(self.id)
