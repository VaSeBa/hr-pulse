"""Тесты для hr_pulse.core.snils.

Номера ниже — официальный пример из документации (112-233-445 95) и номера,
подобранные алгоритмом под нужную контрольную сумму. Они не взяты из реальных документов.
"""

import pytest

from hr_pulse.core.snils import SnilsError, is_valid_snils, snils_checksum, snils_digits

# ---------- snils_digits: приводим к 11 цифрам ----------


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("112-233-445 95", id="standard-format"),
        pytest.param("11223344595", id="digits-only"),
        pytest.param("  112 233 445 95 ", id="spaces"),
        pytest.param("112-233-445\xa095", id="nbsp-from-1c"),
    ],
)
def test_snils_digits_normalizes(raw):
    assert snils_digits(raw) == "11223344595"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("112-233-445 9", id="too-short"),
        pytest.param("112-233-445 955", id="too-long"),
        pytest.param("абв", id="letters"),
    ],
)
def test_snils_digits_rejects_wrong_length(raw):
    with pytest.raises(SnilsError):
        snils_digits(raw)


def test_snils_error_message_has_no_snils():
    # Защита ПДн: текст ошибки не должен содержать сам номер
    with pytest.raises(SnilsError) as error_info:
        snils_digits("112-233-445 9")
    assert "112" not in str(error_info.value)


# ---------- snils_checksum: контрольное число ----------


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        pytest.param("112233445", 95, id="sum-95-below-100"),
        pytest.param("001001999", 65, id="sum-65-below-100"),
        pytest.param("001508815", 0, id="sum-exactly-100"),
        pytest.param("001437544", 0, id="sum-exactly-101"),
        pytest.param("001698871", 58, id="sum-159-above-101"),
    ],
)
def test_snils_checksum(number, expected):
    assert snils_checksum(number) == expected


# ---------- is_valid_snils: итоговая проверка ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("112-233-445 95", True, id="valid"),
        pytest.param("112-233-445 96", False, id="wrong-checksum"),
        pytest.param("001-508-815 00", True, id="valid-checksum-zero"),
        pytest.param("001-001-998 42", True, id="old-number-no-check"),
        pytest.param("000-000-000 00", False, id="all-zeros"),
        pytest.param("112-233-445", False, id="no-checksum-digits"),
        pytest.param("", False, id="empty"),
    ],
)
def test_is_valid_snils(raw, expected):
    assert is_valid_snils(raw) is expected
