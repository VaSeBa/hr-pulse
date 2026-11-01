"""Тесты для hr_pulse.ingest.reader.

Файлы для чтения создаёт экспорт из шага 1.5 — так тесты проверяют связку
«записали как 1С → прочитали обратно».
"""

import pandas as pd
import pytest
from openpyxl import Workbook

from hr_pulse.demo.export_1c import write_employees_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.reader import LoadedTable, describe, find_header_row, read_1c_table

# ---------- find_header_row: на маленьких таблицах, собранных вручную ----------


def test_header_after_report_title():
    raw = pd.DataFrame(
        [
            [None, None, None, None],
            ["Личные данные сотрудников", None, None, None],
            ["Количество", None, "3", None],
            ["Таб. номер", "ФИО", "Дата приема", "СНИЛС"],
            ["00-1", "Иванов И. И.", "10.01.2024", "112-233-445 95"],
        ]
    )
    assert find_header_row(raw) == 3


def test_header_in_first_row():
    raw = pd.DataFrame([["Таб. номер", "ФИО"], ["00-1", "Иванов И. И."]])
    assert find_header_row(raw) == 0


def test_header_with_some_empty_columns():
    # Строка заголовков заполнена не полностью (есть служебные пустые колонки) — это нормально
    raw = pd.DataFrame(
        [
            ["Отчёт", None, None, None, None],
            ["Таб. номер", None, "ФИО", "Должность", "СНИЛС"],
            ["00-1", None, "Иванов И. И.", "Монтажник", "112-233-445 95"],
        ]
    )
    assert find_header_row(raw) == 1


def test_empty_sheet_raises():
    with pytest.raises(ValueError):
        find_header_row(pd.DataFrame([[None, None], [None, None]]))


# ---------- read_1c_table: на демо-выгрузке из шага 1.5 ----------


@pytest.fixture(scope="module")
def rows():
    return FakeCompany(GeneratorConfig(people=200, seed=3)).generate()


@pytest.fixture(scope="module")
def table(rows, tmp_path_factory):
    path = tmp_path_factory.mktemp("reader") / "employees.xlsx"
    write_employees_report(rows, path, mislabel_fire_date=True)
    return read_1c_table(path)


def test_header_row_is_9(table):
    assert isinstance(table, LoadedTable)
    assert table.header_row == 9  # как в настоящей выгрузке


def test_one_row_per_episode(table, rows):
    assert len(table.frame) == len(rows)


def test_empty_service_columns_dropped(table):
    assert all(isinstance(name, str) for name in table.frame.columns)
    assert len(table.frame.columns) == 11  # 14 колонок минус 3 пустые


def test_columns_as_in_file(table):
    columns = list(table.frame.columns)
    assert columns[0] == "Табельный номер (с префиксами)"
    assert "Адрес места проживания" in columns  # «ловушка» читается как есть


def test_values_are_text(table, rows):
    first_tab = table.frame["Табельный номер (с префиксами)"].iloc[0]
    assert first_tab == rows[0].episode.tab_number


def test_leading_zeros_kept(tmp_path):
    # Табельный номер «00123» не должен превратиться в число 123
    wb = Workbook()
    ws = wb.active
    ws.append(["Таб. номер", "ФИО"])
    ws.append(["00123", "Иванов И. И."])
    path = tmp_path / "zeros.xlsx"
    wb.save(path)
    assert read_1c_table(path).frame["Таб. номер"].iloc[0] == "00123"


def test_describe_has_no_personal_data(table, rows):
    text = describe(table)
    assert text == f"Заголовок в строке 9, строк данных: {len(rows)}, колонок: 11"
    assert rows[0].full_name not in text
