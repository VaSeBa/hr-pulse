"""Тесты для заданий шага 1.5: hr_pulse.core.formats_1c."""

from datetime import date

import pytest

from hr_pulse.core.formats_1c import format_count, ru_date


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(date(2024, 1, 10), "10.01.2024", id="leading-zeros"),
        pytest.param(date(2026, 12, 31), "31.12.2026", id="end-of-year"),
        pytest.param(None, "", id="no-date"),
    ],
)
def test_ru_date(value, expected):
    assert ru_date(value) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        pytest.param(7, "7", id="one-digit"),
        pytest.param(999, "999", id="no-separator"),
        pytest.param(1000, "1\xa0000", id="thousand"),
        pytest.param(47075, "47\xa0075", id="like-real-report"),
        pytest.param(1234567, "1\xa0234\xa0567", id="million"),
    ],
)
def test_format_count(number, expected):
    assert format_count(number) == expected
