from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class Period(BaseModel):
    date_from: date
    date_to: date


class Dashboard(BaseModel):
    pending_requests: int
    quotes_draft: int
    quotes_sent: int
    quotes_expired: int
    follow_ups_red: int
    follow_ups_yellow: int
    bookings_to_request: int
    trips_next_30_days: int
    receivable: int


class RankRow(BaseModel):
    label: str
    count: int
    amount: int


class CommercialIndicators(BaseModel):
    requests_received: int
    quotes_created: int
    quotes_accepted: int
    quotes_rejected: int
    # Aceptadas sobre decididas (aceptadas + rechazadas) en el período.
    conversion_percent: Decimal | None
    sales_count: int
    sales_amount: int
    average_ticket: int | None
    new_clients: int
    top_destinations: list[RankRow]
    sales_by_advisor: list[RankRow]
    sales_by_service_type: list[RankRow]


class FinancialIndicators(BaseModel):
    sales_amount: int
    estimated_profit: int
    margin_percent: Decimal | None
    income: int
    expenses: int
    net: int
    # Lo que los clientes todavía deben de todas las ventas.
    receivable: int
    # Lo que se les debe a los proveedores.
    payable: int


class ReportKind(StrEnum):
    SALES = "sales"
    PAYMENTS = "payments"
    QUOTES = "quotes"
    EXPENSES = "expenses"
    REQUESTS = "requests"


class Report(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[str | int | None]]
