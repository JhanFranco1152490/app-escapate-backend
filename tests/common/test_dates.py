from datetime import UTC, date, datetime

import pytest

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


@pytest.mark.parametrize(
    "birth_date, day, age",
    [
        pytest.param(date(2008, 10, 25), date(2026, 10, 24), 17, id="the-day-before-turning-18"),
        pytest.param(date(2008, 10, 25), date(2026, 10, 25), 18, id="the-birthday"),
        pytest.param(date(2008, 10, 25), date(2026, 12, 31), 18, id="after-the-birthday"),
        pytest.param(date(2026, 10, 25), date(2026, 10, 25), 0, id="born-today"),
        # Quien nació un 29 de febrero cumple años el 1 de marzo en los años no bisiestos.
        pytest.param(date(2008, 2, 29), date(2026, 2, 28), 17, id="leap-day-before"),
        pytest.param(date(2008, 2, 29), date(2026, 3, 1), 18, id="leap-day-after"),
    ],
)
def test_age_on_counts_only_complete_years(birth_date, day, age):
    assert dates.age_on(birth_date, day) == age
