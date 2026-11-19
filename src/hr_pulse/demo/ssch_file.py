"""Демо-файл «ССЧ по месяцам» — как его могла бы прислать бухгалтерия.

ССЧ считаем из выдуманных эпизодов: средняя списочная за месяц (шаг 6.2),
уменьшенная на полпроцента — в настоящей ССЧ не учитываются, например,
отпуска по уходу за ребёнком. Одна строка нарочно испорчена («н/д»), чтобы
загрузка показала, как она сообщает об ошибках.
"""

from pathlib import Path

from openpyxl import Workbook

from hr_pulse.analytics.departments import days_in_period, overlap_days, period_dates
from hr_pulse.analytics.turnover import months_between
from hr_pulse.db.ssch import month_label
from hr_pulse.demo.generator import FakeRow

SSCH_SHARE = 0.995  # ССЧ ≈ 99,5 % средней списочной
BROKEN_MONTH = "2023-12"  # строка с «н/д» вместо числа


def demo_ssch(rows: list[FakeRow], month: str) -> float:
    """ССЧ за месяц по выдуманным эпизодам, с одним знаком после запятой."""
    first, last = period_dates(month, month)
    total = sum(overlap_days(r.episode.hire_date, r.episode.fire_date, first, last) for r in rows)
    return round(total / days_in_period(first, last) * SSCH_SHARE, 1)


def write_ssch_report(rows: list[FakeRow], path: Path, start: str, end: str) -> None:
    """Файл: заголовок отчёта, пустая строка, таблица «Месяц | ССЧ»."""
    wb = Workbook()
    ws = wb.active
    ws.title = "ССЧ"
    ws.append(["Среднесписочная численность по месяцам (Демо-Строй)"])
    ws.append([])
    ws.append(["Месяц", "ССЧ"])
    ws.append([month_label(BROKEN_MONTH), "н/д"])
    for month in months_between(start, end):
        ws.append([month_label(month), demo_ssch(rows, month)])
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 10
    wb.save(path)
