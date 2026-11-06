"""Тесты шага 3.2: объединение сотрудников и причин увольнений по табельному номеру."""

import math
from datetime import date

import pandas as pd
import pytest

from hr_pulse.core.fields import Field
from hr_pulse.demo.export_1c import write_employees_report, write_reasons_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.merge import (
    REASON_DATE,
    clean_tab_number,
    date_mismatches,
    describe_merge,
    load_mapped,
    merge_reasons,
)

# ---------- clean_tab_number (задание 1) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("ДМ-00012", "ДМ-00012", id="already-clean"),
        pytest.param(" дм-00012 ", "ДМ-00012", id="spaces-and-case"),
        pytest.param("ДМ-000\xa012", "ДМ-00012", id="nbsp-inside"),
        pytest.param("00123", "00123", id="leading-zeros-kept"),
        pytest.param(None, None, id="none"),
        pytest.param(math.nan, None, id="nan"),
        pytest.param("   ", None, id="only-spaces"),
    ],
)
def test_clean_tab_number(value, expected):
    assert clean_tab_number(value) == expected


# ---------- date_mismatches (задание 2) ----------


def test_date_mismatches_counts_only_known_reason_dates():
    frame = pd.DataFrame(
        {
            "fire_date": [date(2024, 1, 10), date(2024, 2, 1), None, date(2024, 3, 5)],
            REASON_DATE: [date(2024, 1, 10), date(2024, 2, 2), date(2024, 4, 1), None],
        }
    )
    # совпало · расходится · у сотрудника пусто, а причина знает дату · причины нет
    assert date_mismatches(frame) == 2


# ---------- merge_reasons на маленьких таблицах ----------


def make_employees(rows):
    return pd.DataFrame(
        rows, columns=["tab_number", "full_name", "snils", "hire_date", "fire_date"]
    )


def make_reasons(rows):
    return pd.DataFrame(rows, columns=["tab_number", "fire_date", "fire_reason"])


EMPLOYEES = make_employees(
    [
        ["ДМ-1", "Иванов И. И.", "112-233-445 95", "10.01.2022", "15.03.2024"],
        ["ДМ-2", "Петров П. П.", "112-233-445 96", "01.02.2023", None],
        ["ДМ-3", "Сидоров С. С.", "112-233-445 97", "01.02.2021", "01.06.2022"],
    ]
)


def test_reason_attached_by_tab_number():
    result = merge_reasons(EMPLOYEES, make_reasons([["дм-1 ", "15.03.2024", "Переезд"]]))
    reasons = dict(zip(result.frame["tab_number"], result.frame["fire_reason"], strict=True))
    assert reasons["ДМ-1"] == "Переезд"
    assert pd.isna(reasons["ДМ-2"])


def test_full_name_dropped():
    result = merge_reasons(EMPLOYEES, make_reasons([]))
    assert "full_name" not in result.frame.columns


def test_all_episodes_kept_and_dates_parsed():
    result = merge_reasons(EMPLOYEES, make_reasons([]))
    assert len(result.frame) == 3
    assert result.frame["hire_date"].iloc[0] == date(2022, 1, 10)


def test_problems_are_counted():
    reasons = make_reasons(
        [
            ["ДМ-1", "15.03.2024", "Переезд"],
            ["ДМ-1", "15.03.2024", "Переезд"],  # повтор
            ["ДМ-9", "01.05.2024", "Зарплата"],  # нет такого эпизода
            ["ДМ-3", "02.06.2022", "Семья"],  # дата расходится на день
        ]
    )
    result = merge_reasons(EMPLOYEES, reasons)
    assert result.reasons_total == 4
    assert result.duplicate_reasons == 1
    assert result.orphan_reasons == 1
    assert result.date_mismatches == 1
    assert len(result.frame) == 3  # повтор не размножил эпизод


def test_fired_without_reason():
    result = merge_reasons(EMPLOYEES, make_reasons([["ДМ-1", "15.03.2024", "Переезд"]]))
    assert result.fired_without_reason == 1  # ДМ-3 уволен, причины нет


def test_missing_column_explained():
    with pytest.raises(ValueError, match="Дата увольнения"):
        merge_reasons(EMPLOYEES.drop(columns=["fire_date"]), make_reasons([]))


# ---------- на демо-выгрузках ----------


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    rows = FakeCompany(GeneratorConfig(people=200, seed=3)).generate()
    folder = tmp_path_factory.mktemp("merge")
    write_employees_report(rows, folder / "e.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, folder / "r.xlsx", period="01.01.2024 - 30.09.2026")
    employees = load_mapped(folder / "e.xlsx", {"Адрес места проживания": Field.FIRE_DATE})
    return rows, merge_reasons(employees, load_mapped(folder / "r.xlsx"))


def test_demo_every_reason_linked(demo):
    rows, result = demo
    with_reason = sum(1 for row in rows if row.episode.fire_reason is not None)
    assert result.frame["fire_reason"].notna().sum() == with_reason
    assert result.orphan_reasons == 0
    assert result.date_mismatches == 0


def test_demo_reason_matches_generator(demo):
    rows, result = demo
    by_tab = dict(zip(result.frame["tab_number"], result.frame["fire_reason"], strict=True))
    for row in rows:
        if row.episode.fire_reason is not None:
            assert by_tab[row.episode.tab_number] == row.episode.fire_reason


def test_describe_has_only_numbers(demo):
    rows, result = demo
    text = "\n".join(describe_merge(result))
    assert rows[0].episode.tab_number not in text
    assert rows[0].full_name not in text
