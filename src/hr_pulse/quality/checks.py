"""Проверки качества данных в выгрузке сотрудников.

Каждая проверка отвечает на один вопрос («у кого пустой СНИЛС?») и возвращает
номера строк Excel, где проблема найдена. Номер строки — не персональные данные:
по нему вы откроете файл и исправите ячейку, а на экране не будет ни ФИО, ни СНИЛС.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import pandas as pd

from hr_pulse.core.fields import Field, get_spec
from hr_pulse.core.formats_1c import is_blank, parse_ru_date
from hr_pulse.core.snils import is_valid_snils
from hr_pulse.ingest.merge import clean_tab_number

BLANK_IS_ERROR = (Field.TAB_NUMBER, Field.SNILS, Field.HIRE_DATE, Field.POSITION, Field.DEPARTMENT)
DATE_FIELDS = (Field.HIRE_DATE, Field.FIRE_DATE)
ROWS_SHOWN = 10  # сколько номеров строк показывать на экране


class Severity(StrEnum):
    """Насколько серьёзна проблема."""

    ERROR = "ошибка"  # с такими данными аналитика будет неверной
    WARNING = "предупреждение"  # стоит проверить, но считать можно


@dataclass(frozen=True)
class Issue:
    """Одна найденная проблема: что не так и в каких строках Excel."""

    title: str
    severity: Severity
    rows: tuple[int, ...]


def safe_date(value: object) -> date | None:
    """Дата из текста, а если её нет или это не дата — None (без ошибки)."""
    try:
        return parse_ru_date(value)
    except ValueError:
        return None


def bad_date(value: object) -> bool:
    """True, если в ячейке что-то есть, но это не дата («31.02.2024», «уволен»)."""
    if is_blank(value):
        return False
    try:
        parse_ru_date(value)
    except ValueError:
        return True
    return False


def fire_before_hire(hire: object, fire: object) -> bool:
    """True, если обе даты есть и увольнение раньше приёма."""
    fire_day = safe_date(fire)
    hire_day = safe_date(hire)
    if hire_day is None or fire_day is None:
        return False
    return fire_day < hire_day


def in_future(value: object, today: date) -> bool:
    """True, если в ячейке дата и она позже сегодняшнего дня."""
    day = safe_date(value)
    return day is not None and day > today


def rows_where(flags: Iterable[bool], source_rows: tuple[int, ...]) -> tuple[int, ...]:
    """Номера строк Excel там, где флаг True."""
    return tuple(row for row, flag in zip(source_rows, flags, strict=True) if flag)


def check_blanks(frame: pd.DataFrame, source_rows: tuple[int, ...]) -> list[Issue]:
    """Пустые значения в обязательных полях."""
    issues = []
    for field in BLANK_IS_ERROR:
        if field.value not in frame.columns:
            continue  # поля нет в выгрузке — об этом скажет сопоставление колонок
        flags = frame[field.value].map(is_blank)
        title = f"{get_spec(field).title}: пусто"
        issues.append(Issue(title, Severity.ERROR, rows_where(flags, source_rows)))
    return issues


def check_snils(frame: pd.DataFrame, source_rows: tuple[int, ...]) -> list[Issue]:
    """СНИЛС заполнен, но неправильный: не 11 цифр или не сходится контрольное число."""
    column = frame[Field.SNILS.value]
    flags = [not is_blank(v) and not is_valid_snils(str(v)) for v in column]
    title = "СНИЛС: неверный (не 11 цифр или не сходится контрольное число)"
    return [Issue(title, Severity.ERROR, rows_where(flags, source_rows))]


def check_dates(frame: pd.DataFrame, source_rows: tuple[int, ...], today: date) -> list[Issue]:
    """Не даты в колонках дат, увольнение раньше приёма, даты из будущего."""
    issues = []
    for field in DATE_FIELDS:
        if field.value not in frame.columns:
            continue
        column = frame[field.value]
        title = get_spec(field).title
        bad = column.map(bad_date)
        issues.append(Issue(f"{title}: не дата", Severity.ERROR, rows_where(bad, source_rows)))
        future = [in_future(value, today) for value in column]
        later = f"{title}: позже сегодняшнего дня"
        issues.append(Issue(later, Severity.WARNING, rows_where(future, source_rows)))

    if {Field.HIRE_DATE.value, Field.FIRE_DATE.value} <= set(frame.columns):
        pairs = zip(frame[Field.HIRE_DATE.value], frame[Field.FIRE_DATE.value], strict=True)
        flags = [fire_before_hire(hire, fire) for hire, fire in pairs]
        title = "Дата увольнения раньше даты приёма"
        issues.append(Issue(title, Severity.ERROR, rows_where(flags, source_rows)))
    return issues


def check_duplicate_tabs(frame: pd.DataFrame, source_rows: tuple[int, ...]) -> list[Issue]:
    """Один табельный номер в нескольких строках: эпизод должен быть один."""
    tabs = frame[Field.TAB_NUMBER.value].map(clean_tab_number)
    flags = tabs.notna() & tabs.duplicated(keep=False)  # keep=False — отметить ВСЕ повторы
    title = "Табельный номер повторяется"
    return [Issue(title, Severity.ERROR, rows_where(flags, source_rows))]


def run_checks(
    frame: pd.DataFrame, source_rows: tuple[int, ...], today: date | None = None
) -> list[Issue]:
    """Все проверки разом. Возвращает только проблемы, которые нашлись."""
    today = today or date.today()
    issues = check_blanks(frame, source_rows)
    if Field.SNILS.value in frame.columns:
        issues += check_snils(frame, source_rows)
    issues += check_dates(frame, source_rows, today)
    if Field.TAB_NUMBER.value in frame.columns:
        issues += check_duplicate_tabs(frame, source_rows)
    return [issue for issue in issues if issue.rows]


def describe_issues(issues: list[Issue]) -> list[str]:
    """Итог для экрана: проблема, сколько строк и первые номера строк Excel."""
    if not issues:
        return ["Проблем не найдено"]
    lines = []
    for issue in issues:
        shown = ", ".join(str(row) for row in issue.rows[:ROWS_SHOWN])
        more = f" и ещё {len(issue.rows) - ROWS_SHOWN}" if len(issue.rows) > ROWS_SHOWN else ""
        lines.append(f"[{issue.severity}] {issue.title} — {len(issue.rows)}")
        lines.append(f"   строки Excel: {shown}{more}")
    return lines
