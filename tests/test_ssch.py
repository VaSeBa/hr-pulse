"""Тесты шага 5.4: ССЧ по месяцам и коэффициент текучести."""

import math
from datetime import date, datetime

import pandas as pd
import pytest

from hr_pulse.db.ssch import (
    describe_turnover,
    get_ssch,
    list_ssch,
    month_label,
    parse_month,
    parse_ssch,
    set_ssch,
    turnover_for_month,
)
from hr_pulse.db.storage import connect, upsert_episodes

# ---------- разобранный пример ----------


def test_month_label():
    assert month_label("2026-10") == "10.2026"


# ---------- Задача 1: parse_month ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("10.2026", "2026-10", id="ordinary"),
        pytest.param("3.2026", "2026-03", id="one-digit-month"),
        pytest.param("03.2026", "2026-03", id="leading-zero"),
        pytest.param(" 12.2025 ", "2025-12", id="spaces-around"),
    ],
)
def test_parse_month(text, expected):
    assert parse_month(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("13.2026", id="month-13"),
        pytest.param("0.2026", id="month-0"),
        pytest.param("10.26", id="short-year"),
        pytest.param("10/2026", id="slash"),
        pytest.param("10.10.2026", id="full-date"),
        pytest.param("окт.2026", id="letters"),
    ],
)
def test_parse_month_rejects(text):
    with pytest.raises(ValueError, match="10.2026"):
        parse_month(text)


def test_month_round_trip():
    assert month_label(parse_month("7.2026")) == "07.2026"


# ---------- Задача 2: parse_ssch ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("549,5", 549.5, id="comma"),
        pytest.param("549.5", 549.5, id="dot"),
        pytest.param("1 545,3", 1545.3, id="space-thousands"),
        pytest.param("1\xa0545,3", 1545.3, id="nbsp-thousands"),
        pytest.param("557", 557.0, id="integer"),
        pytest.param(557, 557.0, id="number-not-text"),
    ],
)
def test_parse_ssch(value, expected):
    assert parse_ssch(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),
        pytest.param(math.nan, id="nan"),
        pytest.param("пятьсот", id="words"),
        pytest.param("0", id="zero"),
        pytest.param("-3", id="negative"),
    ],
)
def test_parse_ssch_rejects(value):
    with pytest.raises(ValueError):
        parse_ssch(value)


# ---------- хранение ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


NOW = datetime(2026, 11, 15, 20, 30)


def test_set_and_get(conn):
    assert get_ssch(conn, "2026-10") is None
    assert set_ssch(conn, "2026-10", 549.5, now=NOW) is None  # раньше не было
    assert get_ssch(conn, "2026-10") == 549.5


def test_correction_returns_previous(conn):
    set_ssch(conn, "2026-10", 549.5, now=NOW)
    assert set_ssch(conn, "2026-10", 550.0, now=NOW) == 549.5
    assert get_ssch(conn, "2026-10") == 550.0
    assert len(list_ssch(conn)) == 1  # исправили, а не добавили


def test_list_in_month_order(conn):
    set_ssch(conn, "2026-10", 550.0, now=NOW)
    set_ssch(conn, "2026-09", 557.0, now=NOW)
    assert list_ssch(conn) == [("2026-09", 557.0), ("2026-10", 550.0)]


# ---------- коэффициент текучести ----------


def episodes():
    return pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4", "5"],
            "snils": ["112-233-445 95"] * 5,
            "hire_date": [date(2024, 1, 1)] * 5,
            "fire_date": [
                date(2026, 10, 1),
                date(2026, 10, 31),
                date(2026, 10, 15),
                date(2026, 9, 30),
                None,
            ],
            "counts_in_turnover": [True, True, False, True, None],
        }
    )


def test_dismissed_only_counted_and_in_month(conn):
    upsert_episodes(conn, episodes())
    turnover = turnover_for_month(conn, "2026-10")
    assert turnover.dismissed == 2  # «не входит» и сентябрьский не считаются


def test_turnover_percent(conn):
    upsert_episodes(conn, episodes())
    set_ssch(conn, "2026-10", 50.0, now=NOW)
    turnover = turnover_for_month(conn, "2026-10")
    assert turnover.percent == pytest.approx(4.0)  # 2 / 50 × 100
    assert describe_turnover(turnover) == (
        "10.2026: ССЧ 50,0 · уволено (входит в текучесть) 2 · коэффициент текучести 4,00 %"
    )


def test_without_ssch_no_percent(conn):
    upsert_episodes(conn, episodes())
    turnover = turnover_for_month(conn, "2026-10")
    assert turnover.percent is None
    assert "ССЧ не введена" in describe_turnover(turnover)
