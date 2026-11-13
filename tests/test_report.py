"""Тесты шага 4.3: отчёт о качестве данных в Excel."""

from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from hr_pulse.core.fields import Field
from hr_pulse.demo.dirty import spoil_employees
from hr_pulse.demo.export_1c import write_employees_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.mapping import apply_mapping, map_columns
from hr_pulse.ingest.reader import read_1c_table
from hr_pulse.quality.checks import Issue, Severity, run_checks, short_rows
from hr_pulse.quality.report import FILLS, issue_rows, write_quality_report

TODAY = date(2026, 11, 1)

# ---------- short_rows (задание 1) ----------


@pytest.mark.parametrize(
    ("rows", "limit", "expected"),
    [
        pytest.param((12,), 10, "12", id="one"),
        pytest.param((12, 15, 18), 10, "12, 15, 18", id="few"),
        pytest.param((1, 2, 3, 4, 5), 3, "1, 2, 3 и ещё 2", id="cut"),
        pytest.param((1, 2, 3), 3, "1, 2, 3", id="exactly-limit-no-tail"),
        pytest.param((), 10, "", id="empty"),
    ],
)
def test_short_rows(rows, limit, expected):
    assert short_rows(rows, limit) == expected


# ---------- issue_rows (задание 2) ----------

ISSUES = [
    Issue("СНИЛС: пусто", Severity.ERROR, (30, 12)),
    Issue("Дата приёма: позже сегодняшнего дня", Severity.WARNING, (24,)),
    Issue("Должность: пусто", Severity.ERROR, (12,)),
]


def test_issue_rows_one_line_per_row_sorted():
    assert issue_rows(ISSUES) == [
        (12, Severity.ERROR, "Должность: пусто"),
        (12, Severity.ERROR, "СНИЛС: пусто"),
        (24, Severity.WARNING, "Дата приёма: позже сегодняшнего дня"),
        (30, Severity.ERROR, "СНИЛС: пусто"),
    ]


def test_issue_rows_empty():
    assert issue_rows([]) == []


# ---------- write_quality_report ----------


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "Качество.xlsx"
    write_quality_report(ISSUES, path, source=Path("Сотрудники.xlsx"), sheet="Лист_1", today=TODAY)
    return load_workbook(path)


def test_two_sheets(report):
    assert report.sheetnames == ["Сводка", "Строки"]


def test_summary_one_line_per_issue(report):
    ws = report["Сводка"]
    assert [cell.value for cell in ws[1]] == [
        "Серьёзность",
        "Проблема",
        "Строк",
        "Первые строки Excel",
    ]
    assert [cell.value for cell in ws[2]] == ["ошибка", "СНИЛС: пусто", 2, "30, 12"]
    assert ws["A6"].value == "Файл: Сотрудники.xlsx"
    assert ws["B6"].value == "Проверено: 01.11.2026"


def test_rows_sheet_sorted_with_links(report):
    ws = report["Строки"]
    assert [ws.cell(row=r, column=1).value for r in range(2, 6)] == [12, 12, 24, 30]
    assert ws["D2"].hyperlink.target == "Сотрудники.xlsx#'Лист_1'!A12"


def test_colors_by_severity(report):
    ws = report["Строки"]
    error_color = FILLS[Severity.ERROR].fgColor.rgb
    warning_color = FILLS[Severity.WARNING].fgColor.rgb
    assert ws["A2"].fill.fgColor.rgb == error_color
    assert ws["A4"].fill.fgColor.rgb == warning_color  # строка 24 — предупреждение


def test_header_frozen_and_filtered(report):
    ws = report["Строки"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:D5"


def test_empty_report_has_only_headers(tmp_path):
    path = tmp_path / "empty.xlsx"
    write_quality_report([], path, source=Path("x.xlsx"), sheet="Лист_1", today=TODAY)
    assert load_workbook(path)["Строки"].max_row == 1


# ---------- на испорченной демо: в отчёте нет персональных данных ----------


def test_report_has_no_personal_data(tmp_path):
    rows = FakeCompany(GeneratorConfig(people=100, seed=7)).generate()
    source = tmp_path / "dirty.xlsx"
    write_employees_report(rows, source, mislabel_fire_date=True)
    spoil_employees(source)

    table = read_1c_table(source)
    mapping = map_columns(table.frame, {"Адрес места проживания": Field.FIRE_DATE})
    issues = run_checks(apply_mapping(table.frame, mapping), table.source_rows, today=TODAY)
    path = tmp_path / "report.xlsx"
    write_quality_report(issues, path, source=source, sheet="Лист_1", today=TODAY)

    wb = load_workbook(path)
    text = " ".join(
        str(value) for ws in wb for row in ws.iter_rows(values_only=True) for value in row
    )
    for row in rows[:30]:
        assert row.episode.snils not in text
        assert row.full_name not in text
        assert row.episode.tab_number not in text
    assert wb["Строки"].max_row - 1 == sum(len(issue.rows) for issue in issues)
