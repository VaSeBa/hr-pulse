"""Тесты шага 5.3: журнал загрузок и защита от загрузки «задним числом»."""

import math
from datetime import date, datetime

import pandas as pd
import pytest

from hr_pulse.db.journal import (
    BackdatedLoadError,
    Load,
    check_not_backdated,
    format_load,
    last_data_date,
    latest_event,
    list_loads,
    record_load,
)
from hr_pulse.db.storage import LoadStats, connect

# ---------- Задача 1: latest_event ----------


@pytest.mark.parametrize(
    ("hire", "fire", "expected"),
    [
        pytest.param(
            [date(2024, 1, 10), date(2024, 2, 1)], [None, None], date(2024, 2, 1), id="only-hires"
        ),
        pytest.param(
            [date(2024, 1, 10), date(2024, 2, 1)],
            [date(2024, 3, 31), None],
            date(2024, 3, 31),
            id="fire-is-latest",
        ),
        pytest.param(
            [date(2024, 5, 1), date(2024, 2, 1)],
            [None, date(2024, 3, 31)],
            date(2024, 5, 1),
            id="hire-is-latest",
        ),
        pytest.param(
            [date(2024, 1, 10)], [math.nan], date(2024, 1, 10), id="nan-from-pandas-skipped"
        ),
        pytest.param([None], [None], None, id="no-dates-at-all"),
    ],
)
def test_latest_event(hire, fire, expected):
    frame = pd.DataFrame({"hire_date": hire, "fire_date": fire})
    assert latest_event(frame) == expected


def test_latest_event_without_fire_column():
    frame = pd.DataFrame({"hire_date": [date(2024, 1, 10)]})
    assert latest_event(frame) == date(2024, 1, 10)


def test_latest_event_empty_table():
    assert latest_event(pd.DataFrame({"hire_date": [], "fire_date": []})) is None


# ---------- Задача 2: format_load ----------


def test_format_load_example_from_pdf():
    load = Load(
        id=2,
        loaded_at=datetime(2026, 11, 15, 9, 5),
        source="Сотрудники_октябрь.xlsx",
        data_date=date(2026, 10, 31),
        new=40,
        changed=54,
        same=2175,
    )
    assert format_load(load) == (
        "№2 · 15.11.2026 09:05 · Сотрудники_октябрь.xlsx · данные на 31.10.2026 · "
        "новых 40, изменилось 54, без изменений 2175"
    )


def test_format_load_zero_padding():
    load = Load(1, datetime(2026, 1, 3, 7, 0), "f.xlsx", date(2026, 1, 1), 0, 0, 0)
    assert format_load(load).startswith("№1 · 03.01.2026 07:00 · f.xlsx · данные на 01.01.2026")


# ---------- журнал в базе ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


STATS = LoadStats(new=3, changed=1, same=0)


def test_empty_journal(conn):
    assert list_loads(conn) == []
    assert last_data_date(conn) is None


def test_record_and_list(conn):
    first = record_load(conn, "sep.xlsx", date(2026, 9, 30), STATS, now=datetime(2026, 10, 1, 9, 0))
    second = record_load(
        conn, "oct.xlsx", date(2026, 10, 31), STATS, now=datetime(2026, 11, 2, 9, 0)
    )
    assert (first, second) == (1, 2)
    loads = list_loads(conn)
    assert [load.source for load in loads] == ["sep.xlsx", "oct.xlsx"]
    assert loads[1].loaded_at == datetime(2026, 11, 2, 9, 0)
    assert loads[0].new == 3


def test_last_data_date_is_the_latest_not_the_last(conn):
    record_load(conn, "oct.xlsx", date(2026, 10, 31), STATS)
    record_load(conn, "sep.xlsx", date(2026, 9, 30), STATS)  # загрузили позже, но данные старше
    assert last_data_date(conn) == date(2026, 10, 31)


def test_backdated_load_is_stopped(conn):
    record_load(conn, "oct.xlsx", date(2026, 10, 31), STATS)
    with pytest.raises(BackdatedLoadError, match="31.10.2026"):
        check_not_backdated(conn, date(2026, 9, 30))


@pytest.mark.parametrize(
    "data_date",
    [date(2026, 10, 31), date(2026, 11, 30)],
    ids=["same-date-ok", "newer-ok"],
)
def test_same_or_newer_is_fine(conn, data_date):
    record_load(conn, "oct.xlsx", date(2026, 10, 31), STATS)
    check_not_backdated(conn, data_date)  # не бросает ошибку


def test_first_load_is_always_fine(conn):
    check_not_backdated(conn, date(2021, 1, 1))
