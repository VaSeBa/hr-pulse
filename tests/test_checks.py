"""Тесты шага 2.3: сверка с «Количество» из шапки отчёта (hr_pulse.ingest.checks)."""

import pandas as pd
import pytest

from hr_pulse.demo.export_1c import write_employees_report, write_reasons_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.checks import (
    CountCheck,
    CountStatus,
    check_count,
    check_table,
    count_people,
    describe_check,
)
from hr_pulse.ingest.reader import read_1c_table

# ---------- check_count (задание): чистая логика на числах ----------


@pytest.mark.parametrize(
    ("expected", "rows", "people", "status"),
    [
        pytest.param(None, 10, 8, CountStatus.NO_COUNT, id="no-count-in-header"),
        pytest.param(10, 10, 8, CountStatus.ROWS, id="equals-rows"),
        pytest.param(8, 10, 8, CountStatus.PEOPLE, id="equals-people"),
        pytest.param(10, 10, 10, CountStatus.ROWS, id="rows-checked-first"),
        pytest.param(7, 10, 8, CountStatus.MISMATCH, id="nothing-matches"),
        pytest.param(7, 10, None, CountStatus.MISMATCH, id="no-snils-column"),
    ],
)
def test_check_count(expected, rows, people, status):
    assert check_count(expected, rows, people) is status


# ---------- count_people ----------


def test_count_people_counts_distinct_snils():
    frame = pd.DataFrame({"СНИЛС": ["1", "1", "2", None], "ФИО": ["А", "А", "Б", "В"]})
    assert count_people(frame) == 2  # пустой СНИЛС не считается человеком


def test_count_people_without_snils_column():
    assert count_people(pd.DataFrame({"ФИО": ["А"]})) is None


# ---------- describe_check: только числа ----------


def test_describe_people_explains_rehires():
    check = CountCheck(expected=8, rows=10, people=8, status=CountStatus.PEOPLE)
    assert "повторные приёмы" in describe_check(check)
    assert "на 2" in describe_check(check)


def test_describe_mismatch_is_loud():
    check = CountCheck(expected=7, rows=10, people=8, status=CountStatus.MISMATCH)
    assert describe_check(check).startswith("НЕ СХОДИТСЯ")


# ---------- на демо-выгрузках ----------


@pytest.fixture(scope="module")
def rows():
    return FakeCompany(GeneratorConfig(people=200, seed=3)).generate()


def test_demo_employees_count_is_people(rows, tmp_path):
    path = tmp_path / "employees.xlsx"
    write_employees_report(rows, path)
    check = check_table(read_1c_table(path))
    assert check.expected == 200  # в шапке демо — число людей
    assert check.rows == len(rows)  # строк больше: повторные приёмы
    assert check.status is CountStatus.PEOPLE


def test_demo_reasons_has_no_count(rows, tmp_path):
    path = tmp_path / "reasons.xlsx"
    write_reasons_report(rows, path, period="01.01.2024 - 30.09.2026")
    assert check_table(read_1c_table(path)).status is CountStatus.NO_COUNT
