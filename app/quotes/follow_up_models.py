"""Seguimientos comerciales de una cotización y su semáforo.

El color no se guarda: se calcula con la fecha de Bogotá cada vez que se consulta, así no
hace falta una tarea programada que lo actualice.
"""

from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Text
from sqlmodel import Field, Relationship, SQLModel

from app.accounts.models import UserAccount
from app.common.columns import foreign_key, in_values, primary_key, timestamp
from app.common.dates import today
from app.quotes.models import Quote


class FollowUpChannel(StrEnum):
    CALL = "call"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    MEETING = "meeting"
    OTHER = "other"


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"


class AlertColor(StrEnum):
    # Vencido sin registrar.
    RED = "red"
    # Vence hoy o mañana.
    YELLOW = "yellow"
    # Programado más adelante.
    GREEN = "green"


def alert_color(due_date: date, day: date) -> AlertColor:
    if due_date < day:
        return AlertColor.RED
    if due_date <= day + timedelta(days=1):
        return AlertColor.YELLOW
    return AlertColor.GREEN


class QuoteFollowUp(SQLModel, table=True):
    __tablename__ = "quote_follow_up"
    __table_args__ = (
        CheckConstraint(in_values("channel", FollowUpChannel), name="ck_follow_up_channel"),
        CheckConstraint(in_values("status", FollowUpStatus), name="ck_follow_up_status"),
        CheckConstraint("(status = 'done') = (done_at IS NOT NULL)", name="ck_follow_up_done_at"),
    )

    id: int | None = primary_key()
    quote_id: int = foreign_key("quote.id", ondelete="RESTRICT", index=True)
    due_date: date = Field(index=True)
    channel: str = Field(max_length=10)
    purpose: str = Field(max_length=300)
    status: str = Field(default=FollowUpStatus.PENDING, max_length=10, index=True)
    outcome: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    done_at: datetime | None = timestamp(nullable=True)
    done_by_id: int | None = foreign_key("user_account.id", ondelete="RESTRICT", nullable=True)
    created_by_id: int = foreign_key("user_account.id", ondelete="RESTRICT")
    created_at: datetime | None = timestamp()

    quote: Quote = Relationship()
    created_by: UserAccount = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[QuoteFollowUp.created_by_id]"}
    )
    done_by: UserAccount | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[QuoteFollowUp.done_by_id]"}
    )

    @property
    def alert(self) -> AlertColor | None:
        if self.status != FollowUpStatus.PENDING:
            return None
        return alert_color(self.due_date, today())
