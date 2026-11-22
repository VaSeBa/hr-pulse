"""Демо «вашего» отчёта о текучести — эталон для приёмочного теста (шаг 6.4).

Отчёт посчитан из тех же выдуманных эпизодов, но «по-старому», как его могли
бы считать в Excel: по старому справочнику, где увольнение за несоблюдение ПВТР
ещё считалось текучестью. Из-за этого в части строк уволенных больше, чем у
HR Pulse, — приёмочный тест должен это поймать, а --details — объяснить.
Кт записан в формате процента Excel (0,0323 → «3,23 %»).
"""

from pathlib import Path

from openpyxl import Workbook

from hr_pulse.analytics.departments import days_in_period, overlap_days, period_dates
from hr_pulse.demo.export_1c import EXCLUDED_REASONS
from hr_pulse.demo.generator import FakeRow
from hr_pulse.demo.ssch_file import SSCH_SHARE

OLD_RULE_REASON = "Несоблюдение ПВТР"  # по старому справочнику — «Входит»


def counts_old_way(reason: str | None) -> bool:
    """Входит ли причина в текучесть по «старому» справочнику отчёта."""
    if reason is None:
        return False
    return reason not in EXCLUDED_REASONS or reason == OLD_RULE_REASON


def report_rows(rows: list[FakeRow], month: str) -> list[list]:
    """Строки отчёта за месяц: по каждому ОП и «Итого»."""
    first, last = period_dates(month, month)
    days = days_in_period(first, last)
    person_days: dict[str, int] = {}
    dismissed: dict[str, int] = {}
    for row in rows:
        episode, name = row.episode, row.unit.top_department
        overlap = overlap_days(episode.hire_date, episode.fire_date, first, last)
        person_days[name] = person_days.get(name, 0) + overlap
        fired_now = episode.fire_date is not None and first <= episode.fire_date <= last
        if fired_now and counts_old_way(episode.fire_reason):
            dismissed[name] = dismissed.get(name, 0) + 1
    label = f"{month[5:]}.{month[:4]}"
    result = []
    total_ssch, total_dismissed = 0.0, 0
    for name in sorted(person_days):
        if person_days[name] == 0:
            continue
        ssch = round(person_days[name] / days * SSCH_SHARE, 1)
        count = dismissed.get(name, 0)
        result.append([label, name, count, ssch, round(count / ssch, 4)])
        total_ssch += ssch
        total_dismissed += count
    total_ssch = round(total_ssch, 1)
    result.append(
        [label, "Итого", total_dismissed, total_ssch, round(total_dismissed / total_ssch, 4)]
    )
    return result


def write_turnover_report(rows: list[FakeRow], path: Path, months: list[str]) -> None:
    """Файл «Текучесть по подразделениям» — шапка и таблица."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Текучесть"
    ws.append(["Текучесть по подразделениям (Демо-Строй)"])
    ws.append([])
    ws.append(["Месяц", "Подразделение", "Уволено", "ССЧ", "Кт, %"])
    for month in months:
        for line in report_rows(rows, month):
            ws.append(line)
            ws.cell(row=ws.max_row, column=5).number_format = "0.00%"
    for column, width in zip("ABCDE", (10, 20, 10, 10, 8), strict=True):
        ws.column_dimensions[column].width = width
    wb.save(path)
