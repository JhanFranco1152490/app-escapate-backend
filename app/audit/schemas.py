from datetime import date, datetime

from pydantic import BaseModel

from app.audit.models import DeletionKind
from app.common.schemas import OutputSchema, UserRef


class DeletionFilters(BaseModel):
    kind: DeletionKind | None = None


class DeletionOut(OutputSchema):
    id: int
    kind: DeletionKind
    record_id: int
    sale_id: int | None
    description: str
    amount: int
    occurred_on: date | None
    deleted_by: UserRef
    deleted_at: datetime
