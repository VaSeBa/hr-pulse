"""Тесты шага 6.3: динамика текучести по месяцам."""

from datetime import date, datetime

import pandas as pd
import pytest

from hr_pulse.analytics.dynamics import (
    cell,
    data_months,
    format_change,
    month_line,
    previous_year_month,
    year_months,
    year_summary,
)
from hr_pulse.db.ssch import set_ssch
from hr_pulse.db.storage import connect, upsert_episodes

# ---------- разобранные примеры ----------


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        pytest.param("2026-03", "2025-03", id="march"),
        pytest.param("2026-01", "2025-01", id="january"),
    ],
)
def test_previous_year_month(month, expected):
    assert previous_year_month(month) == expected


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        pytest.param(None, 1, "—", id="none"),
        pytest.param(527.5, 1, "527,5", id="number"),
        pytest.param(4.7393, 2, "4,74", id="two-digits"),
    ],
)
def test_cell(value, digits, expected):
    assert cell(value, digits) == expected


# ---------- Задача 2: format_change ----------


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        pytest.param(5.0, 4.0, "+1,00 п.п.", id="up"),
        pytest.param(3.6, 4.0, "−0,40 п.п.", id="down"),
        pytest.param(4.0, 4.0, "0,00 п.п.", id="same"),
        pytest.param(4.001, 4.0, "0,00 п.п.", id="tiny-is-zero"),
        pytest.param(6.36, 5.15, "+1,21 п.п.", id="real"),
        pytest.param(None, 4.0, "—", id="no-current"),
        pytest.param(4.0, None, "—", id="no-previous"),
        pytest.param(None, None, "—", id="nothing"),
    ],
)
def test_format_change(current, previous, expected):
    assert format_change(current, previous) == expected


def test_format_change_uses_real_minus():
    assert format_change(1.0, 2.0).startswith("−")  # U+2212, а не дефис
    assert not format_change(1.0, 2.0).startswith("-")


# ---------- месяцы года ----------


@pytest.mark.parametrize(
    ("year", "expected_len", "first", "last"),
    [
        pytest.param(2026, 10, "2026-01", "2026-10", id="current-year"),
        pytest.param(2025, 12, "2025-01", "2025-12", id="full-year"),
        pytest.param(2021, 9, "2021-04", "2021-12", id="data-starts-in-april"),
    ],
)
def test_year_months(year, expected_len, first, last):
    months = year_months(year, "2021-04", "2026-10")
    assert len(months) == expected_len
    assert (months[0], months[-1]) == (first, last)


@pytest.mark.parametrize("year", [2020, 2027])
def test_year_months_outside_data(year):
    assert year_months(year, "2021-04", "2026-10") == []


# ---------- по базе ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


NOW = datetime(2026, 11, 19)


def fill(conn):
    episodes = pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4"],
            "snils": ["112-233-445 95"] * 4,
            "hire_date": [date(2024, 1, 10)] * 4,
            "fire_date": [date(2025, 3, 5), date(2026, 3, 10), date(2026, 3, 20), None],
            "counts_in_turnover": [True, True, True, None],
        }
    )
    upsert_episodes(conn, episodes)
    set_ssch(conn, "2025-03", 100.0, now=NOW)
    set_ssch(conn, "2026-03", 50.0, now=NOW)


def test_data_months(conn):
    fill(conn)
    assert data_months(conn) == ("2024-01", "2026-03")


def test_data_months_empty(conn):
    assert data_months(conn) is None


def test_month_line(conn):
    fill(conn)
    line = month_line(conn, "2026-03")
    assert line.split() == ["03.2026", "50,0", "2", "4,00", "1,00", "+3,00", "п.п."]


def test_year_summary(conn):
    fill(conn)
    assert year_summary(conn, ["2026-03"]) == "03.2026: 4,00 % · 03.2025: 1,00 % · +3,00 п.п."
