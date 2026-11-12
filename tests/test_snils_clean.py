"""Тесты шага 4.2: один человек — один вид СНИЛС."""

import math
from datetime import date

import pandas as pd
import pytest

from hr_pulse.core.snils import clean_snils, restore_zeros
from hr_pulse.ingest.merge import merge_reasons
from hr_pulse.ingest.rehires import mark_rehires
from hr_pulse.quality.checks import check_snils, check_snils_forms

# ---------- restore_zeros (задание 1) ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("1234567890", "01234567890", id="one-zero-lost"),
        pytest.param("234567890", "00234567890", id="two-zeros-lost"),
        pytest.param("11223344595", "11223344595", id="already-11"),
        pytest.param("112-233-445 95", "112-233-445 95", id="with-dashes-untouched"),
        pytest.param("12345", "00000012345", id="short-number-padded"),
        pytest.param("", "", id="empty-untouched"),
    ],
)
def test_restore_zeros(text, expected):
    assert restore_zeros(text) == expected


# ---------- clean_snils (задание 2) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("112-233-445 95", "112-233-445 95", id="already-clean"),
        pytest.param("11223344595", "112-233-445 95", id="digits-only"),
        pytest.param(" 112 233 445 95 ", "112-233-445 95", id="spaces"),
        pytest.param("1234567890", "012-345-678 90", id="lost-zero"),
        pytest.param("112-233-445", None, id="nine-digits-with-dashes"),
        pytest.param("112-233-445 9555", None, id="too-many"),
        pytest.param(None, None, id="none"),
        pytest.param(math.nan, None, id="nan"),
    ],
)
def test_clean_snils(value, expected):
    assert clean_snils(value) == expected


def test_three_records_one_person():
    records = ["112-233-445 95", "11223344595", " 112 233 445 95"]
    assert len({clean_snils(record) for record in records}) == 1


# ---------- проверки качества ----------

ROWS = (10, 11, 12, 13)


def frame_with(snils_values):
    return pd.DataFrame({"snils": snils_values})


def test_lost_zeros_is_warning_not_error():
    lost = "1234567819"  # 012-345-678 19 без нуля — правильный СНИЛС
    assert clean_snils(lost) is not None
    frame = frame_with([lost, "112-233-445 95", None, "112-233-445 95"])
    assert check_snils(frame, ROWS)[0].rows == ()  # не «неверный»
    lost_issue, _ = check_snils_forms(frame, ROWS)
    assert lost_issue.rows == (10,)


def test_different_forms_of_one_person():
    frame = frame_with(["112-233-445 95", "11223344595", "112-233-445 95", None])
    _, forms_issue = check_snils_forms(frame, ROWS)
    assert forms_issue.rows == (10, 11, 12)  # все строки этого человека


def test_same_form_is_fine():
    frame = frame_with(["112-233-445 95", "112-233-445 95", None, None])
    _, forms_issue = check_snils_forms(frame, ROWS)
    assert forms_issue.rows == ()


# ---------- склейка и повторные приёмы ----------


def test_rehire_found_across_formats():
    employees = pd.DataFrame(
        {
            "tab_number": ["ДМ-1", "ДМ-2"],
            "snils": ["112-233-445 95", "11223344595"],  # один человек, разные записи
            "hire_date": ["10.01.2022", "01.04.2023"],
            "fire_date": ["31.03.2023", None],
        }
    )
    reasons = pd.DataFrame(columns=["tab_number", "fire_date", "fire_reason"])
    merged = merge_reasons(employees, reasons).frame
    assert merged["snils"].nunique() == 1
    result = mark_rehires(merged)
    assert result.rehired_people == 1
    assert result.technical == 1
    assert merged["hire_date"].iloc[1] == date(2023, 4, 1)
