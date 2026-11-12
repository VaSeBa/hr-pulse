"""Тесты шага 4.1: проверки качества данных и номера строк Excel."""

import math
from datetime import date

import pandas as pd
import pytest
from openpyxl import Workbook

from hr_pulse.core.fields import Field
from hr_pulse.demo.dirty import spoil_employees
from hr_pulse.demo.export_1c import write_employees_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.mapping import apply_mapping, map_columns
from hr_pulse.ingest.reader import read_1c_table
from hr_pulse.quality.checks import (
    Severity,
    bad_date,
    describe_issues,
    fire_before_hire,
    rows_where,
    run_checks,
)

TODAY = date(2026, 11, 1)  # «сегодня» в тестах — фиксированное, чтобы тесты не устаревали

# ---------- bad_date (задание 1) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("10.01.2024", False, id="good-date"),
        pytest.param("2024-01-10 00:00:00", False, id="excel-date"),
        pytest.param("31.02.2024", True, id="no-such-day"),
        pytest.param("уволен", True, id="word"),
        pytest.param(None, False, id="empty-is-not-bad"),
        pytest.param(math.nan, False, id="nan-is-not-bad"),
        pytest.param("  ", False, id="spaces-is-not-bad"),
    ],
)
def test_bad_date(value, expected):
    assert bad_date(value) is expected


# ---------- fire_before_hire (задание 2) ----------


@pytest.mark.parametrize(
    ("hire", "fire", "expected"),
    [
        pytest.param("10.01.2024", "01.12.2023", True, id="fire-earlier"),
        pytest.param("10.01.2024", "10.01.2024", False, id="same-day-is-ok"),
        pytest.param("10.01.2024", "11.01.2024", False, id="normal"),
        pytest.param("10.01.2024", None, False, id="still-working"),
        pytest.param(None, "01.12.2023", False, id="no-hire-date"),
        pytest.param("31.02.2024", "01.12.2023", False, id="bad-date-checked-elsewhere"),
    ],
)
def test_fire_before_hire(hire, fire, expected):
    assert fire_before_hire(hire, fire) is expected


# ---------- rows_where ----------


def test_rows_where():
    assert rows_where([False, True, False, True], (10, 11, 15, 16)) == (11, 16)


# ---------- run_checks на маленькой таблице ----------


def make_frame():
    return pd.DataFrame(
        {
            "tab_number": ["ДМ-1", "ДМ-2", "дм-2 ", "ДМ-4"],
            "position": ["Монтажник", None, "Сварщик", "Сварщик"],
            "department": ["Участок 1"] * 4,
            "hire_date": ["10.01.2024", "01.02.2024", "31.02.2024", "01.01.2030"],
            "fire_date": [None, "01.01.2024", None, None],
            "snils": ["112-233-445 95", "", "112-233-445 96", "112-233-445 95"],
        }
    )


ROWS = (10, 11, 13, 14)  # номера строк Excel (12-я была пустой и выброшена)


def issues_by_title():
    return {issue.title: issue for issue in run_checks(make_frame(), ROWS, today=TODAY)}


def test_each_problem_found_with_excel_rows():
    found = {title: issue.rows for title, issue in issues_by_title().items()}
    assert found == {
        "Должность: пусто": (11,),
        "СНИЛС: пусто": (11,),
        "СНИЛС: неверный (не 11 цифр или не сходится контрольное число)": (13,),
        "Дата приёма: не дата": (13,),
        "Дата приёма: позже сегодняшнего дня": (14,),
        "Дата увольнения раньше даты приёма": (11,),
        "Табельный номер повторяется": (11, 13),  # «ДМ-2» и «дм-2 » — один номер
    }


def test_future_is_warning_others_are_errors():
    issues = issues_by_title()
    assert issues["Дата приёма: позже сегодняшнего дня"].severity is Severity.WARNING
    assert issues["СНИЛС: пусто"].severity is Severity.ERROR


def test_clean_data_has_no_issues():
    frame = make_frame().iloc[[0]]
    assert run_checks(frame, (10,), today=TODAY) == []
    assert describe_issues([]) == ["Проблем не найдено"]


def test_missing_column_is_skipped():
    frame = make_frame().drop(columns=["snils", "fire_date"])
    titles = {issue.title for issue in run_checks(frame, ROWS, today=TODAY)}
    assert not any("СНИЛС" in title for title in titles)


def test_describe_shows_rows_not_data():
    text = "\n".join(describe_issues(run_checks(make_frame(), ROWS, today=TODAY)))
    assert "строки Excel: 11, 13" in text
    assert "112-233-445" not in text  # СНИЛС на экран не попадает
    assert "ДМ-2" not in text  # табельные номера тоже


def test_describe_cuts_long_list():
    frame = pd.DataFrame({"position": [None] * 15})
    rows = tuple(range(10, 25))
    text = "\n".join(describe_issues(run_checks(frame, rows, today=TODAY)))
    assert "и ещё 5" in text


# ---------- номера строк Excel из reader ----------


def test_source_rows_skip_header_and_empty_rows(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Отчёт"])  # строка 1
    ws.append(["Таб. номер", "Должность"])  # строка 2 — заголовок
    ws.append(["ДМ-1", "Монтажник"])  # строка 3
    ws.append([None, None])  # строка 4 — пустая, будет выброшена
    ws.append(["ДМ-2", "Сварщик"])  # строка 5
    path = tmp_path / "rows.xlsx"
    wb.save(path)
    assert read_1c_table(path).source_rows == (3, 5)


# ---------- на испорченной демо-выгрузке ----------


def test_every_planted_error_found(tmp_path):
    rows = FakeCompany(GeneratorConfig(people=100, seed=7)).generate()
    path = tmp_path / "dirty.xlsx"
    write_employees_report(rows, path, mislabel_fire_date=True)
    planted = spoil_employees(path)

    table = read_1c_table(path)
    mapping = map_columns(table.frame, {"Адрес места проживания": Field.FIRE_DATE})
    issues = run_checks(apply_mapping(table.frame, mapping), table.source_rows, today=TODAY)
    found = {issue.title: list(issue.rows) for issue in issues}

    assert found["СНИЛС: пусто"] == planted["snils_blank"]
    assert (
        found["СНИЛС: неверный (не 11 цифр или не сходится контрольное число)"]
        == (planted["snils_invalid"])
    )
    assert found["Дата приёма: не дата"] == planted["not_a_date"]
    assert found["Дата увольнения раньше даты приёма"] == planted["fire_before_hire"]
    assert found["Дата приёма: позже сегодняшнего дня"] == planted["future"]
    assert found["Табельный номер повторяется"] == planted["duplicate_tab"]
    assert found["Должность: пусто"] == planted["position_blank"]
    assert (
        found["СНИЛС хранился как число — потерялись ведущие нули"] == (planted["snils_lost_zeros"])
    )
    assert found["СНИЛС одного человека записан по-разному"] == planted["snils_forms"]
    assert len(found) == 9  # и ничего лишнего
