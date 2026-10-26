"""Тесты для заданий шага 1.1: format_snils и mask_snils.

Сначала эти тесты падают — функций ещё нет. Ваша задача — написать функции так,
чтобы все тесты стали зелёными. Сами тесты не меняйте.
"""

import pytest

from hr_pulse.core.snils import SnilsError, format_snils, mask_snils


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("11223344595", id="digits-only"),
        pytest.param("112 233 445 95", id="spaces"),
        pytest.param("112-233-445 95", id="already-formatted"),
    ],
)
def test_format_snils(raw):
    assert format_snils(raw) == "112-233-445 95"


def test_format_snils_rejects_wrong_length():
    with pytest.raises(SnilsError):
        format_snils("123")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("112-233-445 95", "***-***-*** 95", id="formatted"),
        pytest.param("11223344595", "***-***-*** 95", id="digits-only"),
        pytest.param("123", "***-***-*** **", id="broken-masked-fully"),
        pytest.param("", "***-***-*** **", id="empty-masked-fully"),
    ],
)
def test_mask_snils(raw, expected):
    assert mask_snils(raw) == expected
