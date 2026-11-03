"""Тесты шага 2.2: разбор текста из выгрузок 1С обратно в даты и числа."""

import math
from datetime import date

import pytest

from hr_pulse.core.formats_1c import format_count, is_blank, parse_count, parse_ru_date, ru_date

# ---------- is_blank ----------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, True, id="none"),
        pytest.param(math.nan, True, id="nan-from-pandas"),
        pytest.param("", True, id="empty-string"),
        pytest.param("   ", True, id="only-spaces"),
        pytest.param("0", False, id="zero-is-value"),
        pytest.param("Монтажник", False, id="text"),
    ],
)
def test_is_blank(value, expected):
    assert is_blank(value) is expected


# ---------- parse_ru_date ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("10.01.2024", date(2024, 1, 10), id="1c-text"),
        pytest.param(" 31.12.2026 ", date(2026, 12, 31), id="spaces-around"),
        pytest.param("2024-01-10 00:00:00", date(2024, 1, 10), id="excel-date-as-text"),
        pytest.param("2024-01-10", date(2024, 1, 10), id="iso"),
        pytest.param(None, None, id="none"),
        pytest.param(math.nan, None, id="nan"),
        pytest.param("", None, id="empty"),
    ],
)
def test_parse_ru_date(text, expected):
    assert parse_ru_date(text) == expected


@pytest.mark.parametrize("text", ["31.02.2024", "Монтажник", "10/01/2024", "112-233-445 95"])
def test_parse_ru_date_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_ru_date(text)


def test_date_round_trip():
    # Туда и обратно: записали как 1С → прочитали → та же дата
    day = date(2023, 3, 8)
    assert parse_ru_date(ru_date(day)) == day


# ---------- parse_count (задание) ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("7", 7, id="one-digit"),
        pytest.param("47\xa0075", 47075, id="nbsp-like-1c"),
        pytest.param("1 234 567", 1234567, id="ordinary-spaces"),
        pytest.param(" 12 ", 12, id="spaces-around"),
    ],
)
def test_parse_count(text, expected):
    assert parse_count(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(None, id="none"),
        pytest.param("", id="empty"),
        pytest.param("сорок", id="words"),
        pytest.param("12,5", id="fraction"),
    ],
)
def test_parse_count_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_count(text)


@pytest.mark.parametrize("number", [0, 999, 1000, 47075, 1234567])
def test_count_round_trip(number):
    assert parse_count(format_count(number)) == number
