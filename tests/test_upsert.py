"""Тесты шага 5.2: повторная загрузка и помесячная догрузка без дублей."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.core.fields import Field
from hr_pulse.db.storage import (
    LoadStats,
    classify,
    connect,
    count_episodes,
    headcount,
    update_clause,
    upsert_episodes,
)
from hr_pulse.demo.export_1c import write_employees_report, write_reasons_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.demo.monthly import october_rows
from hr_pulse.ingest.merge import load_mapped, merge_reasons
from hr_pulse.ingest.rehires import mark_rehires

# ---------- update_clause (задание 1) ----------


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        pytest.param(("tab_number", "snils"), "snils = excluded.snils", id="one"),
        pytest.param(
            ("tab_number", "snils", "fire_date"),
            "snils = excluded.snils, fire_date = excluded.fire_date",
            id="two",
        ),
        pytest.param(("tab_number",), "", id="only-key"),
    ],
)
def test_update_clause(columns, expected):
    assert update_clause(columns) == expected


# ---------- classify (задание 2) ----------

EXISTING = {
    "ДМ-1": ("ДМ-1", "2024-01-10", None),
    "ДМ-2": ("ДМ-2", "2024-02-01", None),
}


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        pytest.param([("ДМ-1", "2024-01-10", None)], LoadStats(0, 0, 1), id="same"),
        pytest.param([("ДМ-1", "2024-01-10", "2024-10-15")], LoadStats(0, 1, 0), id="fired"),
        pytest.param([("ДМ-9", "2024-10-01", None)], LoadStats(1, 0, 0), id="new"),
        pytest.param(
            [
                ("ДМ-1", "2024-01-10", None),
                ("ДМ-2", "2024-02-01", "2024-10-31"),
                ("ДМ-9", "2024-10-01", None),
            ],
            LoadStats(1, 1, 1),
            id="all-three",
        ),
        pytest.param([], LoadStats(0, 0, 0), id="empty"),
    ],
)
def test_classify(rows, expected):
    assert classify(rows, EXISTING) == expected


def test_classify_empty_database():
    assert classify([("ДМ-1", "2024-01-10", None)], {}) == LoadStats(1, 0, 0)


# ---------- upsert_episodes ----------


def frame(fire_for_first=None, extra=False):
    data = {
        "tab_number": ["ДМ-1", "ДМ-2"],
        "snils": ["112-233-445 95", "112-233-445 96"],
        "hire_date": [date(2024, 1, 10), date(2024, 2, 1)],
        "fire_date": [fire_for_first, None],
    }
    result = pd.DataFrame(data)
    if extra:
        new = {
            "tab_number": "ДМ-3",
            "snils": "112-233-445 97",
            "hire_date": date(2024, 10, 1),
            "fire_date": None,
        }
        result = pd.concat([result, pd.DataFrame([new])], ignore_index=True)
    return result


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_first_load_is_all_new(conn):
    assert upsert_episodes(conn, frame()) == LoadStats(new=2, changed=0, same=0)


def test_second_load_changes_nothing(conn):
    upsert_episodes(conn, frame())
    assert upsert_episodes(conn, frame()) == LoadStats(new=0, changed=0, same=2)
    assert count_episodes(conn) == 2  # дублей нет


def test_next_month_updates_and_adds(conn):
    upsert_episodes(conn, frame())
    stats = upsert_episodes(conn, frame(fire_for_first=date(2024, 10, 15), extra=True))
    assert stats == LoadStats(new=1, changed=1, same=1)
    assert count_episodes(conn) == 3
    (fire,) = conn.execute("SELECT fire_date FROM episodes WHERE tab_number = 'ДМ-1'").fetchone()
    assert fire == "2024-10-15"


def test_history_survives_reload(conn):
    upsert_episodes(conn, frame())
    before = headcount(conn, date(2024, 9, 30))
    upsert_episodes(conn, frame(fire_for_first=date(2024, 10, 15), extra=True))
    assert headcount(conn, date(2024, 9, 30)) == before  # прошлое не изменилось
    assert headcount(conn, date(2024, 10, 31)) == 2  # ДМ-1 ушёл, ДМ-3 пришёл


# ---------- сентябрь → октябрь на демо ----------


def load_demo(rows, folder, name):
    write_employees_report(rows, folder / f"e_{name}.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, folder / f"r_{name}.xlsx", period="01.01.2024 - 31.10.2026")
    employees = load_mapped(folder / f"e_{name}.xlsx", {"Адрес места проживания": Field.FIRE_DATE})
    merged = merge_reasons(employees, load_mapped(folder / f"r_{name}.xlsx")).frame
    return mark_rehires(merged).frame


def test_demo_september_then_october(conn, tmp_path):
    september = FakeCompany(GeneratorConfig(people=300, seed=21)).generate()
    october = october_rows(september)

    upsert_episodes(conn, load_demo(september, tmp_path, "sep"))
    stats = upsert_episodes(conn, load_demo(october, tmp_path, "oct"))

    # Считаем ожидаемое прямо по генератору: кого октябрь изменил (уволил)
    old = {row.episode.tab_number: row.episode for row in september}
    fired = 0
    for row in october:
        before = old.get(row.episode.tab_number)
        if before is not None and before != row.episode:
            fired += 1

    assert stats.new == len(october) - len(september)
    assert stats.changed == fired
    assert stats.same == len(september) - fired
    assert count_episodes(conn) == len(october)
