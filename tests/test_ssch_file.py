"""Тесты шага 6.3: ССЧ из Excel-файла."""

from datetime import datetime

import pytest
from openpyxl import Workbook

from hr_pulse.db.ssch import get_ssch, set_ssch
from hr_pulse.db.ssch_file import (
    SschImport,
    cell_to_month,
    good_numbers,
    import_ssch,
    read_ssch_rows,
    read_table,
)
from hr_pulse.db.storage import connect

# ---------- готовые помощники ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("10.2026", "2026-10", id="text"),
        pytest.param(" 03.2025 ", "2025-03", id="spaces"),
        pytest.param("2026-10-01 00:00:00", "2026-10", id="excel-date"),
        pytest.param("2026-03", "2026-03", id="iso-month"),
    ],
)
def test_cell_to_month(text, expected):
    assert cell_to_month(text) == expected


def test_cell_to_month_bad():
    with pytest.raises(ValueError, match="месяц пишется так"):
        cell_to_month("октябрь")


def test_good_numbers():
    assert good_numbers(["1", "два", "3"]) == ([1, 3], ["два"])


# ---------- Задача 1: read_ssch_rows ----------


def test_read_ssch_rows_good():
    table = [("01.2026", "527,5"), ("02.2026", "529.8")]
    good, errors = read_ssch_rows(table)
    assert good == [("2026-01", 527.5), ("2026-02", 529.8)]
    assert errors == []


def test_read_ssch_rows_bad_value_is_reported_with_row_number():
    table = [("01.2026", "527,5"), ("02.2026", "н/д"), ("03.2026", "539,5")]
    good, errors = read_ssch_rows(table, first_row=4)
    assert good == [("2026-01", 527.5), ("2026-03", 539.5)]  # остальные загрузились
    assert errors == ["строка 5: ССЧ — это число, а не 'н/д'"]


def test_read_ssch_rows_bad_month():
    good, errors = read_ssch_rows([("13.2026", "500")])
    assert good == []
    assert errors == ["строка 2: месяц пишется так: 10.2026, а не '13.2026'"]


def test_read_ssch_rows_empty_value():
    _good, errors = read_ssch_rows([("01.2026", "")])
    assert errors == ["строка 2: ССЧ не указана"]


def test_read_ssch_rows_skips_empty_rows():
    table = [("01.2026", "527,5"), ("", ""), ("03.2026", "539,5")]
    good, errors = read_ssch_rows(table)
    assert len(good) == 2
    assert errors == []


def test_read_ssch_rows_nothing():
    assert read_ssch_rows([]) == ([], [])


# ---------- файл и база ----------


def make_file(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Среднесписочная численность по месяцам"])
    ws.append([])
    ws.append(["Месяц", "Среднесписочная численность"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_read_table_finds_header_below_title(tmp_path):
    path = tmp_path / "ssch.xlsx"
    make_file(path, [["01.2026", 527.5], ["02.2026", "н/д"]])
    table, first_row = read_table(path)
    assert first_row == 4  # данные начинаются с 4-й строки Excel
    assert table == [("01.2026", "527.5"), ("02.2026", "н/д")]


def test_read_table_without_header(tmp_path):
    path = tmp_path / "no_header.xlsx"
    wb = Workbook()
    wb.active.append(["01.2026", 527.5])
    wb.save(path)
    with pytest.raises(ValueError, match="Месяц"):
        read_table(path)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_import_ssch_counts(conn):
    set_ssch(conn, "2026-01", 527.5, now=datetime(2026, 11, 1))
    set_ssch(conn, "2026-02", 500.0, now=datetime(2026, 11, 1))
    pairs = [("2026-01", 527.5), ("2026-02", 529.8), ("2026-03", 539.5)]
    assert import_ssch(conn, pairs) == SschImport(
        added=1, same=1, changed=("02.2026: 500,0 → 529,8",)
    )
    assert get_ssch(conn, "2026-02") == 529.8
