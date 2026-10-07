from datetime import UTC, date, datetime

from app.common import dates


def freeze(monkeypatch, instant: datetime) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(dates, "datetime", FrozenDatetime)


def test_today_is_the_bogota_date_when_utc_already_changed_day(monkeypatch):
    # 04:30 UTC del 6 de octubre son las 23:30 del 5 de octubre en Bogotá.
    freeze(monkeypatch, datetime(2026, 10, 6, 4, 30, tzinfo=UTC))

    assert dates.today() == date(2026, 10, 5)


def test_today_matches_utc_when_both_are_the_same_day(monkeypatch):
    freeze(monkeypatch, datetime(2026, 10, 5, 15, 0, tzinfo=UTC))

    assert dates.today() == date(2026, 10, 5)
