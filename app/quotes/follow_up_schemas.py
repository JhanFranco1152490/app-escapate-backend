from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from app.common.fields import RecordId, optional_multiline_text, required_text
from app.common.schemas import InputSchema, OutputSchema, UserRef
from app.quotes.follow_up_models import AlertColor, FollowUpChannel, FollowUpStatus
from app.quotes.schemas import QuoteClientRef

Purpose = Annotated[str, AfterValidator(required_text(300))]
Outcome = Annotated[str, AfterValidator(optional_multiline_text(2000))]


class FollowUpCreate(InputSchema):
    due_date: date
    channel: FollowUpChannel
    purpose: Purpose


class FollowUpComplete(InputSchema):
    outcome: Outcome | None = None
    # Si el cliente pide que lo vuelvan a contactar: se programa el siguiente en el mismo paso.
    next_due_date: date | None = None
    next_purpose: Purpose | None = None


class FollowUpFilters(BaseModel):
    status: FollowUpStatus | None = None
    alert: AlertColor | None = None
    quote_id: RecordId | None = None
    mine: bool = False


class FollowUpQuoteRef(OutputSchema):
    id: int
    code: str
    destination: str
    client: QuoteClientRef


class FollowUpOut(OutputSchema):
    id: int
    quote: FollowUpQuoteRef
    due_date: date
    channel: FollowUpChannel
    purpose: str
    status: FollowUpStatus
    alert: AlertColor | None
    outcome: str | None
    done_at: datetime | None
    done_by: UserRef | None
    created_by: UserRef
    created_at: datetime


class AlertSummary(BaseModel):
    red: int
    yellow: int
    green: int
