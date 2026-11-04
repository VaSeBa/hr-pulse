"""Проверки прочитанной выгрузки. Первая — сверка с «Количество» из шапки отчёта.

Шапка говорит «2 000», а строк прочитано 2 229 — ошибка чтения или так и надо?
Модуль отвечает на этот вопрос, не показывая ни одного ФИО или СНИЛС: только числа.
"""

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from hr_pulse.core.text import normalize_header
from hr_pulse.ingest.reader import LoadedTable

SNILS_LABEL = "снилс"


class CountStatus(StrEnum):
    """Итог сверки с шапкой отчёта."""

    NO_COUNT = "no_count"  # в шапке нет «Количество» — сверять не с чем
    ROWS = "rows"  # совпало с числом строк
    PEOPLE = "people"  # совпало с числом людей (разных СНИЛС)
    MISMATCH = "mismatch"  # не совпало ни с тем, ни с другим


@dataclass(frozen=True)
class CountCheck:
    """Результат сверки: три числа и вывод по ним."""

    expected: int | None  # из шапки
    rows: int  # строк прочитано
    people: int | None  # разных СНИЛС; None — колонки СНИЛС нет
    status: CountStatus


def count_people(frame: pd.DataFrame) -> int | None:
    """Сколько разных СНИЛС в таблице. Нет колонки СНИЛС — None."""
    for name in frame.columns:
        if normalize_header(str(name)) == SNILS_LABEL:
            return int(frame[name].dropna().nunique())
    return None


def check_count(expected: int | None, rows: int, people: int | None) -> CountStatus:
    """С чем совпало число из шапки: со строками, с людьми или ни с чем."""
    if expected is None:
        return CountStatus.NO_COUNT
    if expected == rows:
        return CountStatus.ROWS
    if expected == people:
        return CountStatus.PEOPLE
    return CountStatus.MISMATCH


def check_table(table: LoadedTable) -> CountCheck:
    """Собрать три числа и сверить их."""
    rows = len(table.frame)
    people = count_people(table.frame)
    status = check_count(table.report_count, rows, people)
    return CountCheck(expected=table.report_count, rows=rows, people=people, status=status)


def describe_check(check: CountCheck) -> str:
    """Вывод сверки одной фразой — только числа, без персональных данных."""
    match check.status:
        case CountStatus.NO_COUNT:
            return "в шапке нет «Количество» — сверять не с чем"
        case CountStatus.ROWS:
            return f"в шапке {check.expected}, строк {check.rows} — файл прочитан целиком"
        case CountStatus.PEOPLE:
            extra = check.rows - check.people
            return (
                f"в шапке {check.expected} — это число людей (разных СНИЛС); "
                f"строк больше на {extra}: это повторные приёмы"
            )
        case CountStatus.MISMATCH:
            return (
                f"НЕ СХОДИТСЯ: в шапке {check.expected}, строк {check.rows}, "
                f"людей {check.people} — проверьте файл"
            )
