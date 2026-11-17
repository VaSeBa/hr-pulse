"""Тесты шага 6.1: текучесть за период и по подразделениям."""

from datetime import date, datetime

import pandas as pd
import pytest

from hr_pulse.analytics.turnover import (
    NO_DEPARTMENT,
    average_ssch,
    describe_departments,
    describe_period,
    dismissed_by_department,
    months_between,
    next_month,
    period_label,
    period_turnover,
    with_shares,
)
from hr_pulse.db.ssch import set_ssch
from hr_pulse.db.storage import connect, upsert_episodes

# ---------- разобранные примеры ----------


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        pytest.param("2026-10", "2026-11", id="ordinary"),
        pytest.param("2026-09", "2026-10", id="to-two-digits"),
        pytest.param("2026-12", "2027-01", id="new-year"),
    ],
)
def test_next_month(month, expected):
    assert next_month(month) == expected


def test_average_ssch():
    assert average_ssch([557.0, 550.0, 560.0]) == pytest.approx(555.6667, rel=1e-4)


# ---------- Задача 1: months_between ----------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        pytest.param("2026-10", "2026-10", ["2026-10"], id="one-month"),
        pytest.param("2026-07", "2026-09", ["2026-07", "2026-08", "2026-09"], id="quarter"),
        pytest.param(
            "2026-11", "2027-02", ["2026-11", "2026-12", "2027-01", "2027-02"], id="new-year"
        ),
    ],
)
def test_months_between(start, end, expected):
    assert months_between(start, end) == expected


def test_months_between_whole_year():
    months = months_between("2025-01", "2025-12")
    assert len(months) == 12
    assert months[0] == "2025-01"
    assert months[-1] == "2025-12"


def test_months_between_rejects_backwards():
    with pytest.raises(ValueError, match="позже"):
        months_between("2026-10", "2026-07")


# ---------- Задача 2: with_shares ----------


def test_with_shares():
    rows = [("ОП Северное", 3), ("ОП Восточное", 1)]
    assert with_shares(rows) == [
        ("ОП Северное", 3, pytest.approx(75.0)),
        ("ОП Восточное", 1, pytest.approx(25.0)),
    ]


def test_with_shares_one_department_is_100():
    assert with_shares([("ОП Северное", 7)]) == [("ОП Северное", 7, pytest.approx(100.0))]


def test_with_shares_sum_is_100():
    rows = [("А", 1), ("Б", 1), ("В", 1)]
    assert sum(share for _, _, share in with_shares(rows)) == pytest.approx(100.0)


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param([], id="empty"),
        pytest.param([("ОП Северное", 0)], id="zero"),
    ],
)
def test_with_shares_nothing_to_divide(rows):
    assert with_shares(rows) == []


def test_with_shares_keeps_order():
    rows = [("Б", 5), ("А", 2)]
    assert [department for department, _, _ in with_shares(rows)] == ["Б", "А"]


# ---------- текучесть за период ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


NOW = datetime(2026, 11, 17, 21, 0)


def episodes():
    return pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4", "5", "6", "7"],
            "snils": ["112-233-445 95"] * 7,
            "top_department": [
                "ОП Северное",
                "ОП Северное",
                "ОП Восточное",
                "ОП Северное",
                None,
                "ОП Восточное",
                "ОП Северное",
            ],
            "hire_date": [date(2024, 1, 1)] * 7,
            "fire_date": [
                date(2026, 7, 1),
                date(2026, 8, 15),
                date(2026, 9, 30),
                date(2026, 9, 10),
                date(2026, 8, 3),
                date(2026, 6, 30),  # до периода
                date(2026, 8, 20),
            ],
            "counts_in_turnover": [True, True, True, True, True, True, False],
        }
    )


def test_period_dismissed_inside_period_only(conn):
    upsert_episodes(conn, episodes())
    turnover = period_turnover(conn, "2026-07", "2026-09")
    assert turnover.dismissed == 5  # июнь и «не входит» не считаются
    assert turnover.months == 3


def test_period_percent_uses_average_ssch(conn):
    upsert_episodes(conn, episodes())
    for month, value in [("2026-07", 40.0), ("2026-08", 50.0), ("2026-09", 60.0)]:
        set_ssch(conn, month, value, now=NOW)
    turnover = period_turnover(conn, "2026-07", "2026-09")
    assert turnover.ssch == pytest.approx(50.0)
    assert turnover.percent == pytest.approx(10.0)  # 5 / 50 × 100
    assert describe_period(turnover) == (
        "07.2026–09.2026 (3 мес.): средняя ССЧ 50,0 · "
        "уволено (входит в текучесть) 5 · коэффициент текучести 10,00 %"
    )


def test_period_missing_ssch(conn):
    upsert_episodes(conn, episodes())
    set_ssch(conn, "2026-08", 50.0, now=NOW)
    turnover = period_turnover(conn, "2026-07", "2026-09")
    assert turnover.missing == ("2026-07", "2026-09")
    assert turnover.percent is None
    assert describe_period(turnover).endswith(
        "нет ССЧ за 07.2026, 09.2026 — коэффициент не посчитать"
    )


def test_by_department_sorted_and_unnamed(conn):
    upsert_episodes(conn, episodes())
    assert dismissed_by_department(conn, "2026-07", "2026-09") == [
        ("ОП Северное", 3),
        (NO_DEPARTMENT, 1),
        ("ОП Восточное", 1),
    ]


def test_describe_departments():
    assert describe_departments([("ОП Северное", 3, 75.0)]) == ["ОП Северное — 3 (75,0 %)"]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        pytest.param("2026-10", "2026-10", "10.2026", id="one-month"),
        pytest.param("2026-07", "2026-10", "07.2026–10.2026", id="period"),
    ],
)
def test_period_label(start, end, expected):
    assert period_label(start, end) == expected
