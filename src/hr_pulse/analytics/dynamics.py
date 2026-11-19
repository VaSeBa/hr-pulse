"""Динамика текучести: год по месяцам и сравнение с прошлым годом.

Команда:  uv run python -m hr_pulse.analytics.dynamics 2026

Для каждого месяца года (до последнего месяца, за который есть данные):
ССЧ, уволенные (входит в текучесть), коэффициент — и коэффициент того же месяца
год назад. Разница — в процентных пунктах (п.п.): было 4,0 %, стало 5,0 % —
это +1,00 п.п. (а не «+25 %»). Внизу — итог с начала года против того же
периода прошлого года.
"""

import argparse
import sqlite3
from pathlib import Path

from hr_pulse.analytics.turnover import months_between, period_label, period_turnover
from hr_pulse.db.ssch import month_label, ru_number, turnover_for_month
from hr_pulse.db.storage import DEFAULT_DB, connect

# Границы данных в базе: самый ранний приём и самая поздняя дата приёма или увольнения.
DATA_RANGE_SQL = """
SELECT MIN(hire_date), MAX(MAX(hire_date), COALESCE(MAX(fire_date), ''))
FROM episodes
"""

HEADER = f"{'Месяц':<9}{'ССЧ':>8}{'Уволено':>9}{'Кт, %':>8}{'Год назад':>11}  Изменение"


def previous_year_month(month: str) -> str:
    """Тот же месяц год назад: «2026-03» → «2025-03». (Пример к задаче 2.)"""
    year, number = month.split("-")
    return f"{int(year) - 1}-{number}"


def cell(value: float | None, digits: int = 1) -> str:
    """Число для таблицы; None — прочерк."""
    if value is None:  # нет значения — прочерк, а не «None» и не 0
        return "—"
    return ru_number(value, digits)


def format_change(current: float | None, previous: float | None) -> str:
    """Изменение в процентных пунктах: «+1,25 п.п.», «−0,40 п.п.», «0,00 п.п.».

    Нет хотя бы одного из двух значений — прочерк «—».
    """
    if (
        current is None or previous is None
    ):  # ① шаг 1: нет хотя бы одного из двух значений — не с чем сравнивать
        return "—"
    delta = round(
        current - previous, 2
    )  # ② шаг 2: разница «сейчас минус год назад», округлённая до сотых
    if delta > 0:  # шаг 3: знак
        sign = "+"
    elif delta < 0:  # ③ разница отрицательная
        sign = "−"  # настоящий минус «−», а не дефис «-»
    else:
        sign = ""
    return f"{sign}{ru_number(abs(delta), 2)} п.п."  # шаг 4: модуль числа и знак отдельно


def data_months(conn: sqlite3.Connection) -> tuple[str, str] | None:
    """Первый и последний месяц данных в базе: («2021-01», «2026-10»); база пуста — None."""
    first, last = conn.execute(DATA_RANGE_SQL).fetchone()
    return (first[:7], last[:7]) if first else None


def year_months(year: int, first: str, last: str) -> list[str]:
    """Месяцы года, за которые в базе есть данные: (2026, «2021-01», «2026-10») → январь…октябрь."""
    start = max(f"{year}-01", first)
    end = min(f"{year}-12", last)
    return months_between(start, end) if start <= end else []


def month_line(conn: sqlite3.Connection, month: str) -> str:
    """Одна строка таблицы."""
    now = turnover_for_month(conn, month)
    before = turnover_for_month(conn, previous_year_month(month))
    return (
        f"{month_label(month):<9}{cell(now.ssch):>8}{now.dismissed:>9}"
        f"{cell(now.percent, 2):>8}{cell(before.percent, 2):>11}  "
        f"{format_change(now.percent, before.percent)}"
    )


def year_summary(conn: sqlite3.Connection, months: list[str]) -> str:
    """Итог с начала года против того же периода прошлого года."""
    start, end = months[0], months[-1]
    now = period_turnover(conn, start, end)
    before = period_turnover(conn, previous_year_month(start), previous_year_month(end))
    label_now = period_label(start, end)
    label_before = period_label(previous_year_month(start), previous_year_month(end))
    return (
        f"{label_now}: {cell(now.percent, 2)} % · {label_before}: {cell(before.percent, 2)} % · "
        f"{format_change(now.percent, before.percent)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Текучесть по месяцам года и год назад")
    parser.add_argument("year", type=int, help="год, например 2026")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    conn = connect(args.db)
    bounds = data_months(conn)
    months = year_months(args.year, *bounds) if bounds else []
    if not months:
        print(f"{args.year}: в базе нет данных за этот год")
        conn.close()
        return

    print(HEADER)
    for month in months:
        print(month_line(conn, month))
    print()
    print(f"С начала года: {year_summary(conn, months)}")
    conn.close()


if __name__ == "__main__":
    main()
