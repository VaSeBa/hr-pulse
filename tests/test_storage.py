"""Тесты шага 5.1: база SQLite — запись эпизодов и численность на дату запросом SQL."""

import math
import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import pytest

from hr_pulse.core.fields import Field
from hr_pulse.db.storage import (
    COLUMNS,
    connect,
    count_episodes,
    episode_rows,
    headcount,
    save_episodes,
    to_db_value,
)
from hr_pulse.demo.export_1c import write_employees_report, write_reasons_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.demo.summary import headcount_on
from hr_pulse.ingest.merge import load_mapped, merge_reasons
from hr_pulse.ingest.rehires import mark_rehires

# ---------- to_db_value (задание 1) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(date(2024, 1, 10), "2024-01-10", id="date-iso"),
        pytest.param(True, 1, id="true"),
        pytest.param(False, 0, id="false"),
        pytest.param(np.bool_(True), 1, id="numpy-true"),
        pytest.param(None, None, id="none"),
        pytest.param(math.nan, None, id="nan"),
        pytest.param("ДМ-00012", "ДМ-00012", id="text-as-is"),
        pytest.param(np.int64(7), 7, id="numpy-number"),
    ],
)
def test_to_db_value(value, expected):
    result = to_db_value(value)
    assert result == expected
    assert type(result) is type(expected)  # именно int, а не numpy и не bool


def test_iso_dates_sort_like_dates():
    # Почему ISO: как текст «2024-01-10» < «2024-02-01» — так же, как даты.
    # А «10.01.2024» > «01.02.2024» как текст — хотя по датам наоборот (шаг 2.2).
    assert to_db_value(date(2024, 1, 10)) < to_db_value(date(2024, 2, 1))
    assert "10.01.2024" > "01.02.2024"


# ---------- запись и чтение ----------


def small_frame():
    return pd.DataFrame(
        {
            "tab_number": ["ДМ-1", "ДМ-2", "ДМ-3"],
            "snils": ["112-233-445 95", "112-233-445 96", "112-233-445 97"],
            "position": ["Монтажник", "Сварщик", "Табельщик"],
            "department": ["Участок 1"] * 3,
            "hire_date": [date(2024, 1, 10), date(2024, 2, 1), date(2024, 3, 1)],
            "fire_date": [date(2024, 3, 31), None, None],
            "fire_reason": ["Оплата труда: низкая зп", None, None],
            "is_technical": [False, False, False],
        }
    )


@pytest.fixture
def conn():
    connection = connect(":memory:")  # база в памяти — для тестов, файл не нужен
    yield connection
    connection.close()


def test_rows_in_columns_order():
    first = episode_rows(small_frame())[0]
    assert len(first) == len(COLUMNS)
    assert first[COLUMNS.index("hire_date")] == "2024-01-10"
    assert first[COLUMNS.index("top_department")] is None  # колонки нет — NULL


def test_save_and_count(conn):
    assert save_episodes(conn, small_frame()) == 3
    assert count_episodes(conn) == 3


def test_values_stored_as_expected(conn):
    save_episodes(conn, small_frame())
    row = conn.execute(
        "SELECT hire_date, fire_date, is_technical, counts_in_turnover "
        "FROM episodes WHERE tab_number = 'ДМ-1'"
    ).fetchone()
    assert row == ("2024-01-10", "2024-03-31", 0, None)


def test_no_full_name_in_database(conn):
    columns = [info[1] for info in conn.execute("PRAGMA table_info(episodes)")]
    assert "full_name" not in columns


def test_same_tab_number_twice_is_refused(conn):
    save_episodes(conn, small_frame())
    with pytest.raises(sqlite3.IntegrityError):
        save_episodes(conn, small_frame())
    assert count_episodes(conn) == 3  # «всё или ничего»: вторая попытка не добавила ни строки


# ---------- численность на дату (задание 2) ----------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2024, 1, 9), 0, id="before-first-hire"),
        pytest.param(date(2024, 1, 10), 1, id="hire-day-counts"),
        pytest.param(date(2024, 3, 1), 3, id="everyone"),
        pytest.param(date(2024, 3, 31), 3, id="fire-day-counts"),
        pytest.param(date(2024, 4, 1), 2, id="day-after-fire"),
    ],
)
def test_headcount(conn, day, expected):
    save_episodes(conn, small_frame())
    assert headcount(conn, day) == expected


def test_sql_matches_python_on_demo(conn, tmp_path):
    rows = FakeCompany(GeneratorConfig(people=300, seed=11)).generate()
    write_employees_report(rows, tmp_path / "e.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, tmp_path / "r.xlsx", period="01.01.2024 - 30.09.2026")
    employees = load_mapped(tmp_path / "e.xlsx", {"Адрес места проживания": Field.FIRE_DATE})
    frame = merge_reasons(employees, load_mapped(tmp_path / "r.xlsx")).frame
    save_episodes(conn, mark_rehires(frame).frame)

    assert count_episodes(conn) == len(rows)
    for day in [date(2021, 6, 30), date(2023, 12, 31), date(2026, 9, 30)]:
        assert headcount(conn, day) == headcount_on(rows, day)  # SQL = Python (шаг 1.4)
