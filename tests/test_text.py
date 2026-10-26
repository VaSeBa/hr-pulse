"""Тесты для hr_pulse.core.text."""

import pytest

from hr_pulse.core.text import normalize_header


def test_lowercase_and_trim():
    raw = "  Дата приема "  # Arrange — подготовили входные данные
    result = normalize_header(raw)  # Act — вызвали проверяемую функцию
    assert result == "дата приема"  # Assert — сравнили с ожидаемым


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Дата приёма", "дата приема", id="yo-to-e"),
        pytest.param("Таб.\xa0номер", "таб номер", id="nbsp-and-dot"),
        pytest.param("СНИЛС", "снилс", id="uppercase"),
        pytest.param("Подразделение.Функциональный блок (Подразделения)",
            "подразделение функциональный блок подразделения",
            id="dots-and-brackets"),
        pytest.param("Табельный номер (с префиксами)",
            "табельный номер с префиксами",
            id="brackets")
    ],
)
def test_normalize_header_cases(raw, expected):
    assert normalize_header(raw) == expected
