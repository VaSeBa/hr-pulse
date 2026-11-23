"""Тесты шага 7.3: светофор рисков."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.analytics.risk import (
    GREEN,
    MIN_MONTHS,
    NO_DATA,
    RED,
    YELLOW,
    assess,
    average,
    describe,
    month_rates,
    risk_level,
    shift_month,
)
from hr_pulse.db.storage import connect, upsert_episodes

# ---------- пример: shift_month ----------


@pytest.mark.parametrize(
    ("month", "delta", "expected"),
    [
        pytest.param("2026-10", -1, "2026-09", id="back-one"),
        pytest.param("2026-01", -1, "2025-12", id="over-new-year"),
        pytest.param("2026-10", -12, "2025-10", id="year-back"),
        pytest.param("2026-12", 1, "2027-01", id="forward"),
        pytest.param("2026-05", 0, "2026-05", id="zero"),
    ],
)
def test_shift_month(month, delta, expected):
    assert shift_month(month, delta) == expected


# ---------- Задача 1: risk_level ----------


@pytest.mark.parametrize(
    ("current", "usual", "dismissed", "expected"),
    [
        pytest.param(9.0, 4.0, 10, RED, id="red"),
        pytest.param(6.0, 4.0, 10, RED, id="red-border-1.5"),
        pytest.param(5.0, 4.0, 10, YELLOW, id="yellow"),
        pytest.param(4.8, 4.0, 10, YELLOW, id="yellow-border-1.2"),
        pytest.param(4.5, 4.0, 10, GREEN, id="green"),
        pytest.param(1.0, 4.0, 10, GREEN, id="below-usual"),
        pytest.param(20.0, 4.0, 2, GREEN, id="too-few-dismissed"),
        pytest.param(9.0, 4.0, 3, RED, id="three-is-enough"),
        pytest.param(None, 4.0, 5, NO_DATA, id="no-current"),
        pytest.param(9.0, None, 5, NO_DATA, id="no-history"),
    ],
)
def test_risk_level(current, usual, dismissed, expected):
    assert risk_level(current, usual, dismissed) == expected


# ---------- Задача 2: average ----------


def test_average():
    assert average([2.0, 4.0, 6.0, 2.0, 4.0, 6.0]) == pytest.approx(4.0)


def test_average_skips_none():
    values = [2.0, None, 4.0, 6.0, None, 2.0, 4.0, 6.0]
    assert average(values) == pytest.approx(4.0)  # None не считаются нулями


def test_average_too_short():
    assert average([5.0] * (MIN_MONTHS - 1) + [None] * 6) is None


def test_average_exactly_min_months():
    assert average([5.0] * MIN_MONTHS) == pytest.approx(5.0)


def test_average_zeros_count():
    assert average([0.0] * 6 + [6.0] * 6) == pytest.approx(3.0)  # ноль — это значение


# ---------- готовые помощники ----------


def test_describe():
    row = (RED, "ОП Центральное", 4, 9.37, 1.67)
    assert describe(row) == (
        "КРАСНЫЙ    ОП Центральное — Кт 9,37 % при обычных 1,67 % (в 5,6 раза) · уволено 4"
    )


def test_describe_no_history():
    assert describe((NO_DATA, "ОП", 0, 0.0, None)) == (
        "НЕТ ДАННЫХ ОП — Кт 0,00 %, истории меньше 6 мес."
    )


@pytest.fixture
def conn():
    connection = connect(":memory:")
    # 30 человек в ОП Северное с 2025 года; по одному уходит в январе–мае 2026,
    # в июне — сразу трое: всплеск
    fire = [date(2026, m, 15) for m in (1, 2, 3, 4, 5)] + [date(2026, 6, d) for d in (3, 4, 5)]
    fire += [None] * 22
    episodes = pd.DataFrame(
        {
            "tab_number": [str(i) for i in range(30)],
            "snils": ["112-233-445 95"] * 30,
            "top_department": ["ОП Северное"] * 30,
            "hire_date": [date(2025, 1, 1)] * 30,
            "fire_date": fire,
            "counts_in_turnover": [True] * 8 + [None] * 22,
        }
    )
    upsert_episodes(connection, episodes)
    yield connection
    connection.close()


def test_month_rates(conn):
    dismissed, rate = month_rates(conn, "2026-06")["ОП Северное"]
    assert dismissed == 3
    assert rate == pytest.approx(3 / 23.1 * 100, rel=0.05)


def test_assess_finds_spike(conn):
    rows = assess(conn, "2026-06")
    level, name, dismissed, current, usual = rows[0]
    assert (level, name, dismissed) == (RED, "ОП Северное", 3)
    assert current > usual * 1.5
