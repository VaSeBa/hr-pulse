"""Тесты шага 6.2: средняя списочная и коэффициент текучести по подразделениям."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.analytics.departments import (
    average_headcount,
    days_in_period,
    department_rates,
    describe_rates,
    month_start,
    overlap_days,
    period_dates,
    person_days,
)
from hr_pulse.analytics.turnover import NO_DEPARTMENT
from hr_pulse.db.storage import connect, upsert_episodes

JULY_1 = date(2026, 7, 1)
SEPT_30 = date(2026, 9, 30)  # III квартал — 92 дня

# ---------- даты периода (готовые функции) ----------


def test_month_start():
    assert month_start("2026-07") == date(2026, 7, 1)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        pytest.param("2026-07", "2026-09", (JULY_1, SEPT_30), id="quarter"),
        pytest.param("2026-02", "2026-02", (date(2026, 2, 1), date(2026, 2, 28)), id="february"),
        pytest.param("2026-12", "2026-12", (date(2026, 12, 1), date(2026, 12, 31)), id="december"),
    ],
)
def test_period_dates(start, end, expected):
    assert period_dates(start, end) == expected


def test_period_dates_backwards():
    with pytest.raises(ValueError, match="позже"):
        period_dates("2026-09", "2026-07")


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        pytest.param(JULY_1, SEPT_30, 92, id="quarter"),
        pytest.param(JULY_1, JULY_1, 1, id="one-day"),
        pytest.param(date(2026, 1, 1), date(2026, 12, 31), 365, id="year"),
    ],
)
def test_days_in_period(first, last, expected):
    assert days_in_period(first, last) == expected


# ---------- Задача 1: overlap_days ----------


@pytest.mark.parametrize(
    ("hire", "fire", "expected"),
    [
        pytest.param(date(2024, 1, 10), None, 92, id="whole-period"),
        pytest.param(date(2026, 9, 1), None, 30, id="hired-inside"),
        pytest.param(date(2024, 1, 10), date(2026, 7, 31), 31, id="fired-inside"),
        pytest.param(date(2026, 8, 1), date(2026, 8, 31), 31, id="both-inside"),
        pytest.param(date(2024, 1, 10), date(2026, 6, 30), 0, id="fired-before"),
        pytest.param(date(2026, 10, 1), None, 0, id="hired-after"),
        pytest.param(date(2024, 1, 10), date(2026, 7, 1), 1, id="fired-on-first-day"),
        pytest.param(date(2026, 9, 30), None, 1, id="hired-on-last-day"),
        pytest.param(date(2026, 7, 1), date(2026, 9, 30), 92, id="exactly-period"),
    ],
)
def test_overlap_days(hire, fire, expected):
    assert overlap_days(hire, fire, JULY_1, SEPT_30) == expected


# ---------- пример к задаче 2: словарь-копилка ----------


def test_person_days():
    rows = [
        ("ОП Северное", "2024-01-10", None),  # весь квартал — 92
        ("ОП Северное", "2026-09-01", None),  # сентябрь — 30
        ("ОП Восточное", "2024-01-10", "2026-07-31"),  # июль — 31
    ]
    assert person_days(rows, JULY_1, SEPT_30) == {"ОП Северное": 122, "ОП Восточное": 31}


# ---------- Задача 2: department_rates ----------


def test_department_rates():
    result = department_rates({"ОП Северное": 50.0}, {"ОП Северное": 5})
    assert result == [("ОП Северное", 50.0, 5, pytest.approx(10.0))]


def test_department_rates_no_dismissed_is_zero():
    result = department_rates({"ОП Центральное": 40.0}, {})
    assert result == [("ОП Центральное", 40.0, 0, 0.0)]


def test_department_rates_sorted_by_percent():
    headcount = {"ОП Большое": 200.0, "ОП Малое": 20.0}
    dismissed = {"ОП Большое": 10, "ОП Малое": 4}  # 5 % и 20 %
    names = [name for name, _, _, _ in department_rates(headcount, dismissed)]
    assert names == ["ОП Малое", "ОП Большое"]  # уволенных меньше, а текучесть выше


def test_department_rates_tie_alphabetical():
    result = department_rates({"Б": 10.0, "А": 10.0}, {"Б": 1, "А": 1})
    assert [name for name, _, _, _ in result] == ["А", "Б"]


def test_department_rates_empty():
    assert department_rates({}, {}) == []


def test_describe_rates():
    assert describe_rates([("ОП Северное", 280.46, 33, 11.766)]) == [
        "ОП Северное — средняя списочная 280,5 · уволено 33 · 11,77 %"
    ]


# ---------- средняя списочная по базе ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_average_headcount(conn):
    episodes = pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4", "5"],
            "snils": ["112-233-445 95"] * 5,
            "top_department": ["ОП Северное", "ОП Северное", "ОП Восточное", None, "ОП Северное"],
            "hire_date": [
                date(2024, 1, 10),  # весь квартал
                date(2026, 9, 1),  # с сентября
                date(2024, 1, 10),
                date(2024, 1, 10),
                date(2024, 1, 10),
            ],
            "fire_date": [
                None,
                None,
                date(2026, 8, 15),
                None,
                date(2026, 6, 30),
            ],  # №5 — до периода
        }
    )
    upsert_episodes(conn, episodes)
    result = average_headcount(conn, "2026-07", "2026-09")
    assert result == {
        "ОП Северное": pytest.approx(122 / 92),
        "ОП Восточное": pytest.approx(46 / 92),  # 31 + 15 дней
        NO_DEPARTMENT: pytest.approx(1.0),
    }
