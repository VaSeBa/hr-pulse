"""Тесты шага 3.1: сопоставление колонок выгрузки с полями шаблона."""

import pandas as pd
import pytest

from hr_pulse.core.fields import Field
from hr_pulse.demo.export_1c import write_employees_report, write_reasons_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.mapping import (
    apply_mapping,
    contains_phrase,
    map_columns,
    match_column,
    missing_required,
)
from hr_pulse.ingest.reader import read_1c_table

# ---------- contains_phrase (задание 1) ----------


@pytest.mark.parametrize(
    ("text", "phrase", "expected"),
    [
        pytest.param("дата приема", "дата приема", True, id="same"),
        pytest.param("прием на работу дата приема", "дата приема", True, id="at-the-end"),
        pytest.param("дата приема сотрудника", "дата приема", True, id="at-the-start"),
        pytest.param("даты приема", "дата приема", False, id="part-of-word"),
        pytest.param("подразделения", "подразделение", False, id="other-ending"),
        pytest.param("должность", "дата приема", False, id="absent"),
    ],
)
def test_contains_phrase(text, phrase, expected):
    assert contains_phrase(text, phrase) is expected


# ---------- match_column: названия из настоящих выгрузок ----------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param("Табельный номер (с префиксами)", Field.TAB_NUMBER, id="tab-prefix"),
        pytest.param("Сотрудник.Таб. номер", Field.TAB_NUMBER, id="tab-reasons"),
        pytest.param("Сотрудник", Field.FULL_NAME, id="employee-is-name"),
        pytest.param("Дата приёма", Field.HIRE_DATE, id="yo"),
        pytest.param("Прием на работу.Дата приема", Field.HIRE_DATE, id="hire-reasons"),
        pytest.param("Увольнение.Дата увольнения", Field.FIRE_DATE, id="fire-reasons"),
        pytest.param("СНИЛС", Field.SNILS, id="snils"),
        pytest.param("Причина по мнению HR", Field.FIRE_REASON, id="reason-hr"),
        pytest.param(
            "Подразделение.Подразделение верхнего уровня (для отчетов) (Подразделения)",
            Field.TOP_DEPARTMENT,
            id="longest-phrase-wins",
        ),
        pytest.param(
            "Должность по штатному расписанию.Подкатегория персонала",
            Field.STAFF_CATEGORY,
            id="category-not-position",
        ),
        pytest.param("Адрес места проживания", None, id="trap-not-guessed"),
        pytest.param("Количество сотрудников", None, id="whole-words-only"),
        pytest.param("Причина по мнению руководителя", None, id="manager-reason-ignored"),
        pytest.param("Увольнение.Статья ТК РФ", None, id="article-unknown"),
    ],
)
def test_match_column(header, expected):
    assert match_column(header) == expected


# ---------- missing_required (задание 2) ----------


def test_nothing_missing():
    everything = {
        Field.TAB_NUMBER,
        Field.POSITION,
        Field.DEPARTMENT,
        Field.HIRE_DATE,
        Field.FIRE_DATE,
        Field.SNILS,
    }
    assert missing_required(everything) == []


def test_missing_in_template_order():
    found = {Field.TAB_NUMBER, Field.POSITION, Field.DEPARTMENT, Field.HIRE_DATE}
    assert missing_required(found) == [Field.FIRE_DATE, Field.SNILS]


def test_optional_fields_never_missing():
    assert Field.FULL_NAME not in missing_required(set())


# ---------- map_columns ----------


def test_duplicate_field_goes_to_duplicates():
    frame = pd.DataFrame(columns=["Таб. номер", "Сотрудник.Таб. номер"])
    mapping = map_columns(frame)
    assert mapping.fields == {"Таб. номер": Field.TAB_NUMBER}
    assert mapping.duplicates == ["Сотрудник.Таб. номер"]


def test_override_beats_automatics():
    frame = pd.DataFrame({"Адрес места проживания": ["10.01.2024"]})
    mapping = map_columns(frame, overrides={"Адрес места проживания": Field.FIRE_DATE})
    assert mapping.fields == {"Адрес места проживания": Field.FIRE_DATE}


@pytest.fixture(scope="module")
def rows():
    return FakeCompany(GeneratorConfig(people=200, seed=3)).generate()


@pytest.fixture(scope="module")
def employees(rows, tmp_path_factory):
    path = tmp_path_factory.mktemp("mapping") / "employees.xlsx"
    write_employees_report(rows, path, mislabel_fire_date=True)
    return read_1c_table(path).frame


def test_trap_column_suggested_for_fire_date(employees):
    mapping = map_columns(employees)
    assert mapping.missing == [Field.FIRE_DATE]
    assert mapping.suggestions == {Field.FIRE_DATE: ["Адрес места проживания"]}


def test_after_override_nothing_missing(employees):
    mapping = map_columns(employees, overrides={"Адрес места проживания": Field.FIRE_DATE})
    assert mapping.missing == []
    assert mapping.suggestions == {}


def test_apply_mapping_renames_and_drops(employees):
    mapping = map_columns(employees, overrides={"Адрес места проживания": Field.FIRE_DATE})
    clean = apply_mapping(employees, mapping)
    assert "fire_date" in clean.columns
    assert "hire_date" in clean.columns
    assert len(clean) == len(employees)
    assert len(clean.columns) == 11  # все 11 колонок демо узнаны


def test_reasons_report_columns(rows, tmp_path):
    path = tmp_path / "reasons.xlsx"
    write_reasons_report(rows, path, period="01.01.2024 - 30.09.2026")
    mapping = map_columns(read_1c_table(path).frame)
    assert mapping.fields["Причина по мнению HR"] is Field.FIRE_REASON
    assert "Организация" in mapping.unknown
    assert mapping.missing == [Field.SNILS]  # в отчёте причин СНИЛС нет
