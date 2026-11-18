"""Коэффициент текучести по подразделениям.

Команда:  uv run python -m hr_pulse.analytics.departments 07.2026 09.2026

ССЧ по подразделениям никто не вводит, поэтому знаменатель программа оценивает
сама — по эпизодам в базе. Это СРЕДНЯЯ СПИСОЧНАЯ численность за период:

    средняя списочная = человеко-дни за период / дней в периоде

Человеко-дни — сколько дней периода каждый сотрудник числился в подразделении,
сложенные по всем сотрудникам. Работал весь квартал — 92 дня, пришёл 1 сентября —
30 дней. День приёма и день увольнения засчитываются (как в шаге 5.1).

Средняя списочная обычно чуть больше ССЧ: в ССЧ по правилам Росстата не входят,
например, сотрудники в отпуске по уходу за ребёнком. Поэтому коэффициент по
подразделениям — оценка, и рядом печатается сравнение с официальной ССЧ.
"""

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from hr_pulse.analytics.turnover import (
    NO_DEPARTMENT,
    dismissed_by_department,
    months_between,
    next_month,
    period_label,
    period_turnover,
)
from hr_pulse.db.ssch import parse_month, ru_number
from hr_pulse.db.storage import DEFAULT_DB, connect

# Эпизоды, которые хоть один день периода были «в списке»:
# приняты не позже конца периода и уволены не раньше его начала (или работают).
IN_PERIOD_SQL = """
SELECT COALESCE(top_department, :none) AS top_name, hire_date, fire_date
FROM episodes
WHERE hire_date <= :end
  AND (fire_date IS NULL OR fire_date >= :start)
"""


def month_start(month: str) -> date:
    """«2026-07» → 1 июля 2026."""
    year, number = month.split("-")
    return date(int(year), int(number), 1)


def period_dates(start: str, end: str) -> tuple[date, date]:
    """Период месяцев → первый и последний день: («2026-07», «2026-09») → 01.07 и 30.09."""
    months_between(start, end)  # проверка: конец не раньше начала (иначе ValueError)
    last_day = month_start(next_month(end)) - timedelta(days=1)  # день до 1-го числа следующего
    return month_start(start), last_day


def days_in_period(first: date, last: date) -> int:
    """Сколько дней от first до last включительно. (Пример к задаче 1.)"""
    return (last - first).days + 1  # 30.09 − 01.07 = 91 день разницы, а дней — 92


def overlap_days(hire: date, fire: date | None, first: date, last: date) -> int:
    """Сколько дней периода [first; last] сотрудник числился: от приёма до увольнения.

    fire = None — работает. Не пересекается с периодом — 0.
    """
    begin = max(hire, first)
    end = last if fire is None else min(fire, last)
    if end < begin:
        return 0
    return days_in_period(begin, end)


def person_days(
    rows: list[tuple[str, str, str | None]], first: date, last: date
) -> dict[str, float]:
    """Человеко-дни по подразделениям. (Пример к задаче 2: словарь-копилка.)"""
    totals: dict[str, float] = {}  # копилка: подразделение → сумма дней
    for name, hire, fire in rows:
        fire_date = date.fromisoformat(fire) if fire else None  # текст из базы → дата
        days = overlap_days(date.fromisoformat(hire), fire_date, first, last)
        totals[name] = totals.get(name, 0) + days  # get(…, 0) — «сколько было, а если не было — 0»
    return totals


def average_headcount(conn: sqlite3.Connection, start: str, end: str) -> dict[str, float]:
    """Средняя списочная численность по подразделениям за период."""
    first, last = period_dates(start, end)
    params = {"start": first.isoformat(), "end": last.isoformat(), "none": NO_DEPARTMENT}
    rows = conn.execute(IN_PERIOD_SQL, params).fetchall()
    days = days_in_period(first, last)
    return {name: total / days for name, total in person_days(rows, first, last).items()}


def department_rates(
    headcount: dict[str, float], dismissed: dict[str, int]
) -> list[tuple[str, float, int, float]]:
    """Подразделение, средняя списочная, уволено, коэффициент % — больше коэффициент выше.

    headcount: {"ОП Северное": 280.5, …}; dismissed: {"ОП Северное": 33, …}.
    Подразделение без увольнений — 0 уволенных и 0 %.
    """
    rows = []
    for name, average in headcount.items():
        count = dismissed.get(name, 0)
        percent = count / average * 100
        rows.append((name, average, count, percent))
    # шаг 3: сортировка — по убыванию коэффициента, при равенстве — по алфавиту
    rows.sort(key=lambda row: (-row[3], row[0]))
    return rows


def describe_rates(rows: list[tuple[str, float, int, float]]) -> list[str]:
    """«ОП Северное — средняя списочная 280,5 · уволено 33 · 11,76 %»."""
    return [
        f"{name} — средняя списочная {ru_number(average)} · уволено {count} · "
        f"{ru_number(percent, 2)} %"
        for name, average, count, percent in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Коэффициент текучести по подразделениям")
    parser.add_argument("start", help="первый месяц, мм.гггг: 07.2026")
    parser.add_argument("end", nargs="?", help="последний месяц (по умолчанию = первый)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    try:
        start = parse_month(args.start)
        end = parse_month(args.end) if args.end else start
        conn = connect(args.db)
        headcount = average_headcount(conn, start, end)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error

    if not headcount:
        print(f"{period_label(start, end)}: в базе нет сотрудников за этот период")
        conn.close()
        return

    total = sum(headcount.values())
    turnover = period_turnover(conn, start, end)
    official = "не введена" if turnover.ssch is None else ru_number(turnover.ssch)
    print(f"{period_label(start, end)}: средняя списочная {ru_number(total)} (ССЧ — {official})")
    print("Коэффициент текучести по подразделениям (оценка по средней списочной):")
    dismissed = dict(dismissed_by_department(conn, start, end))
    for line in describe_rates(department_rates(headcount, dismissed)):
        print(f"  {line}")
    conn.close()


if __name__ == "__main__":
    main()
