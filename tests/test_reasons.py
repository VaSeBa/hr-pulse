"""Тесты шага 3.3: справочник причин «Входит / Не входит в текучесть»."""

import math
from datetime import date

import pandas as pd
import pytest
from openpyxl import Workbook

from hr_pulse.core.fields import Field
from hr_pulse.demo.export_1c import (
    EXCLUDED_REASONS,
    write_employees_report,
    write_reasons_reference,
    write_reasons_report,
)
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.merge import load_mapped, merge_reasons
from hr_pulse.ingest.reasons import (
    COUNTS,
    ReasonBook,
    apply_reference,
    describe_reasons,
    load_reference,
    parse_status,
    reason_key,
)

# ---------- reason_key (задание 1) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("Переезд в другой город", "переезд в другой город", id="ordinary"),
        pytest.param("ПЕРЕЕЗД В ДРУГОЙ ГОРОД", "переезд в другой город", id="upper-like-reference"),
        pytest.param("  Переезд  в другой\xa0город ", "переезд в другой город", id="spaces"),
        pytest.param(
            "Истечение срока патента, согласования ФСБ, др. спец.права",
            "истечение срока патента согласования фсб др спец права",
            id="punctuation",
        ),
        pytest.param("ВЫХОД НА ПЕНСИЮ", "выход на пенсию", id="like-reference-row"),
        pytest.param(None, None, id="none"),
        pytest.param(math.nan, None, id="nan"),
    ],
)
def test_reason_key(value, expected):
    assert reason_key(value) == expected


# ---------- parse_status (задание 2) ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("Входит", True, id="included"),
        pytest.param("Не входит", False, id="excluded"),
        pytest.param("НЕ ВХОДИТ", False, id="upper"),
        pytest.param(" входит ", True, id="spaces"),
    ],
)
def test_parse_status(value, expected):
    assert parse_status(value) is expected


@pytest.mark.parametrize("value", ["Да", "", None, "Входит частично"])
def test_parse_status_rejects_unknown(value):
    with pytest.raises(ValueError):
        parse_status(value)


# ---------- ReasonBook и apply_reference ----------

BOOK = ReasonBook({"переезд в другой город": True, "выход на пенсию": False})


def test_book_counts():
    assert BOOK.counts("ПЕРЕЕЗД В ДРУГОЙ ГОРОД") is True
    assert BOOK.counts("Выход на пенсию") is False
    assert BOOK.counts("Причина, которой нет") is None
    assert BOOK.counts(None) is None


def make_frame():
    return pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4", "5", "6"],
            "fire_date": [date(2024, 1, 1)] * 5 + [None],
            "fire_reason": [
                "Переезд в другой город",
                "переезд в другой город",
                "Выход на пенсию",
                "Не сошлись характерами",
                None,
                None,
            ],
        }
    )


def test_apply_reference_counts():
    summary = apply_reference(make_frame(), BOOK)
    assert summary.included == 2
    assert summary.excluded == 1
    assert summary.without_reason == 1  # уволен, причины нет (работающий не считается)
    assert summary.unknown == {"Не сошлись характерами": 1}


def test_apply_reference_adds_column():
    summary = apply_reference(make_frame(), BOOK)
    assert list(summary.frame[COUNTS].iloc[:3]) == [True, True, False]
    assert COUNTS not in make_frame().columns  # исходная таблица не тронута


def test_describe_lists_unknown_reasons():
    lines = describe_reasons(apply_reference(make_frame(), BOOK))
    assert any("Не сошлись характерами" in line for line in lines)


def test_describe_without_unknown_is_short():
    frame = make_frame().iloc[:3]
    assert len(describe_reasons(apply_reference(frame, BOOK))) == 2


# ---------- load_reference ----------


def write_book(path, rows, header=("Наименование", "Учёт в текучести")):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_load_reference_from_excel(tmp_path):
    path = tmp_path / "book.xlsx"
    write_book(path, [("ПЕРЕЕЗД", "Входит"), ("ВЫХОД НА ПЕНСИЮ", "Не входит")])
    book = load_reference(path)
    assert book.statuses == {"переезд": True, "выход на пенсию": False}


def test_load_reference_bad_status_names_reason(tmp_path):
    path = tmp_path / "book.xlsx"
    write_book(path, [("ПЕРЕЕЗД", "Входит"), ("ВЫХОД НА ПЕНСИЮ", "Может быть")])
    with pytest.raises(ValueError, match="ВЫХОД НА ПЕНСИЮ"):
        load_reference(path)


def test_load_reference_without_status_column(tmp_path):
    path = tmp_path / "book.xlsx"
    write_book(path, [("ПЕРЕЕЗД", "Входит")], header=("Наименование", "Комментарий"))
    with pytest.raises(ValueError, match="текучест"):
        load_reference(path)


# ---------- вся цепочка на демо ----------


def test_demo_every_reason_found_in_reference(tmp_path):
    rows = FakeCompany(GeneratorConfig(people=200, seed=3)).generate()
    write_employees_report(rows, tmp_path / "e.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, tmp_path / "r.xlsx", period="01.01.2024 - 30.09.2026")
    write_reasons_reference(tmp_path / "ref.xlsx")

    employees = load_mapped(tmp_path / "e.xlsx", {"Адрес места проживания": Field.FIRE_DATE})
    merged = merge_reasons(employees, load_mapped(tmp_path / "r.xlsx")).frame
    summary = apply_reference(merged, load_reference(tmp_path / "ref.xlsx"))

    assert summary.unknown == {}
    expected_excluded = sum(1 for row in rows if row.episode.fire_reason in EXCLUDED_REASONS)
    assert summary.excluded == expected_excluded
