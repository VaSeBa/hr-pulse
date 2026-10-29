"""Тесты для заданий шага 1.4: hr_pulse.demo.summary.

Сначала эти тесты падают — модуля ещё нет. Создайте его так,
чтобы все тесты стали зелёными. Сами тесты не меняйте.
"""

from datetime import date

from hr_pulse.core.models import Episode
from hr_pulse.demo.generator import UNITS, FakeRow
from hr_pulse.demo.summary import dismissals_by_year, headcount_on


def make_row(hire: date, fire: date | None) -> FakeRow:
    """Выдуманная строка: важны только даты."""
    episode = Episode("ДМ-00001", "112-233-445 95", "Монтажник", "Участок", hire, fire)
    return FakeRow(episode, "Иванов Иван Иванович", UNITS["field"][0], "Основные")


# Четыре выдуманных эпизода — результат посчитан вручную
ROWS = [
    make_row(date(2023, 3, 1), date(2023, 11, 30)),  # уволен в 2023
    make_row(date(2023, 6, 1), date(2024, 2, 15)),  # уволен в 2024
    make_row(date(2024, 1, 10), date(2024, 1, 20)),  # уволен в 2024
    make_row(date(2024, 5, 1), None),  # работает
]


def test_dismissals_by_year():
    assert dismissals_by_year(ROWS) == {2023: 1, 2024: 2}


def test_dismissals_by_year_empty():
    assert dismissals_by_year([]) == {}


def test_headcount_on():
    assert headcount_on(ROWS, date(2023, 1, 1)) == 0  # ещё никого
    assert headcount_on(ROWS, date(2023, 7, 1)) == 2  # двое приняты в 2023
    assert headcount_on(ROWS, date(2024, 1, 15)) == 2  # 2-й и 3-й
    assert headcount_on(ROWS, date(2024, 2, 15)) == 1  # 2-й в день увольнения ещё числится
    assert headcount_on(ROWS, date(2024, 2, 16)) == 0  # 2-й уволен, 4-й ещё не принят
    assert headcount_on(ROWS, date(2025, 1, 1)) == 1  # только 4-й
