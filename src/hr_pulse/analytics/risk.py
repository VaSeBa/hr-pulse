"""Светофор рисков: в каких ОП текучесть в этом месяце выше обычного.

Команда:  uv run python -m hr_pulse.analytics.risk            — последний месяц в базе
          uv run python -m hr_pulse.analytics.risk 09.2026    — выбранный месяц

Для каждого ОП сравниваем коэффициент текучести за месяц с его ОБЫЧНЫМ уровнем —
средним месячным коэффициентом этого же ОП за предыдущие 12 месяцев:

  КРАСНЫЙ — в 1,5 раза выше обычного и больше;
  ЖЁЛТЫЙ  — в 1,2 раза выше обычного и больше;
  ЗЕЛЁНЫЙ — в пределах обычного;
  при числе уволенных меньше 3 сигнала нет: одно-два увольнения — это случай, а не тенденция.

Сравниваем ОП с самим собой, а не с другими: у вахтового ОП на Севере и у
офисного ОП в городе «нормальная» текучесть разная.
Коэффициент ОП — по средней списочной (шаг 6.2). Печатает только числа и названия ОП.
"""

import argparse
import sqlite3
from pathlib import Path

from hr_pulse.analytics.departments import average_headcount
from hr_pulse.analytics.dynamics import data_months
from hr_pulse.analytics.turnover import dismissed_by_department, months_between
from hr_pulse.db.ssch import month_label, parse_month, ru_number
from hr_pulse.db.storage import DEFAULT_DB, connect

RED, YELLOW, GREEN, NO_DATA = "КРАСНЫЙ", "ЖЁЛТЫЙ", "ЗЕЛЁНЫЙ", "НЕТ ДАННЫХ"
RED_RATIO = 1.5  # во сколько раз выше обычного — красный
YELLOW_RATIO = 1.2  # … — жёлтый
MIN_DISMISSED = 3  # меньше уволенных за месяц — не сигнал
MIN_MONTHS = 6  # меньше месяцев истории — «обычный уровень» не считаем
HISTORY = 12  # сколько месяцев истории смотрим
LEVEL_ORDER = {RED: 0, YELLOW: 1, GREEN: 2, NO_DATA: 3}


def shift_month(month: str, delta: int) -> str:
    """Месяц на delta месяцев вперёд (или назад, если delta < 0): («2026-01», -1) → «2025-12»."""
    year, number = month.split("-")
    index = int(year) * 12 + int(number) - 1 + delta  # месяцы подряд с «нулевого»
    return f"{index // 12}-{index % 12 + 1:02d}"


def average(values: list[float | None]) -> float | None:
    """Среднее только по известным значениям; известных меньше MIN_MONTHS — None. (Задача 2.)"""
    known = [value for value in values if value is not None]
    if len(known) < MIN_MONTHS:
        return None
    return sum(known) / len(known)


def risk_level(current: float | None, usual: float | None, dismissed: int) -> str:
    """Цвет светофора для ОП за месяц. (Задача 1.)"""
    if current is None or usual is None:  # не с чем сравнивать
        return NO_DATA
    if dismissed < MIN_DISMISSED:
        return GREEN
    if current >= usual * RED_RATIO:
        return RED
    if current >= usual * YELLOW_RATIO:
        return YELLOW
    return GREEN


def month_rates(conn: sqlite3.Connection, month: str) -> dict[str, tuple[int, float]]:
    """{ОП: (уволено, коэффициент %)} за один месяц — по средней списочной."""
    headcount = average_headcount(conn, month, month)
    dismissed = dict(dismissed_by_department(conn, month, month))
    return {
        name: (dismissed.get(name, 0), dismissed.get(name, 0) / people * 100)
        for name, people in headcount.items()
        if people > 0
    }


def assess(conn: sqlite3.Connection, month: str) -> list[tuple[str, str, int, float, float | None]]:
    """(цвет, ОП, уволено, Кт за месяц, обычный Кт) — опаснее выше."""
    history = months_between(shift_month(month, -HISTORY), shift_month(month, -1))
    past = [month_rates(conn, m) for m in history]
    rows = []
    for name, (dismissed, current) in month_rates(conn, month).items():
        usual = average([rates[name][1] if name in rates else None for rates in past])
        rows.append((risk_level(current, usual, dismissed), name, dismissed, current, usual))
    # по цвету (красные первыми), внутри цвета — по превышению обычного уровня
    rows.sort(key=lambda r: (LEVEL_ORDER[r[0]], -(r[3] / r[4]) if r[4] else 0, r[1]))
    return rows


def describe(row: tuple[str, str, int, float, float | None]) -> str:
    """«КРАСНЫЙ  ОП Центральное — Кт 9,37 % при обычных 2,10 %: в 4,5 раза выше · уволено 4»."""
    level, name, dismissed, current, usual = row
    if usual is None:
        return f"{level:<11}{name} — Кт {ru_number(current, 2)} %, истории меньше {MIN_MONTHS} мес."
    times = f"в {ru_number(current / usual)} раза" if usual else "обычно 0"
    return (
        f"{level:<11}{name} — Кт {ru_number(current, 2)} % при обычных "
        f"{ru_number(usual, 2)} % ({times}) · уволено {dismissed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Светофор рисков текучести по ОП")
    parser.add_argument("month", nargs="?", help="месяц, мм.гггг (по умолчанию — последний в базе)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    conn = connect(args.db)
    try:
        if args.month:
            month = parse_month(args.month)
        else:
            bounds = data_months(conn)
            if bounds is None:
                print("В базе нет данных")
                return
            month = bounds[1]
        rows = assess(conn, month)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error
    finally:
        conn.close()

    first, last = shift_month(month, -HISTORY), shift_month(month, -1)
    usual_period = f"{month_label(first)}–{month_label(last)}"
    print(f"Риски на {month_label(month)} (обычный уровень — {usual_period}):")
    for row in rows:
        print(f"  {describe(row)}")
    red, yellow = ru_number(RED_RATIO), ru_number(YELLOW_RATIO)
    print(f"Красный — в {red} раза выше обычного, жёлтый — в {yellow}; ", end="")
    print(f"меньше {MIN_DISMISSED} уволенных — не сигнал.")


if __name__ == "__main__":
    main()
