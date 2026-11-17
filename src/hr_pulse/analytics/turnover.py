"""Текучесть за период и по подразделениям.

Команда:  uv run python -m hr_pulse.analytics.turnover 07.2026 10.2026  — за период
          uv run python -m hr_pulse.analytics.turnover 10.2026          — за один месяц

Коэффициент за период считается так же, как за месяц, только знаменатель —
средняя ССЧ за все месяцы периода (так считает Росстат: ССЧ за квартал —
сумма ССЧ трёх месяцев, делённая на 3):

    Кт за период = уволенные за период (входит в текучесть) / средняя ССЧ × 100 %

По подразделениям ССЧ нет (её вводим только по организации), поэтому для
подразделений показываем, сколько из уволенных пришлось на каждое и какую это
составляет долю. Печатает только числа и названия подразделений.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from hr_pulse.db.ssch import ensure_ssch, get_ssch, month_label, parse_month, ru_number
from hr_pulse.db.storage import DEFAULT_DB, connect

NO_DEPARTMENT = "(подразделение не указано)"

# BETWEEN — «от и до включительно». Месяцы «2026-07» сравниваются как текст,
# и порядок у них правильный: «2026-07» < «2026-10» < «2027-01».
PERIOD_DISMISSED_SQL = """
SELECT COUNT(*)
FROM episodes
WHERE counts_in_turnover = 1
  AND substr(fire_date, 1, 7) BETWEEN :start AND :end
"""

# GROUP BY — «сложить в стопки по подразделению и посчитать каждую стопку».
# COALESCE(a, b) — «a, а если a пусто — b».
# Имя top_name нарочно не совпадает с колонкой department: иначе SQLite
# сгруппирует по колонке, а не по нашему выражению (ловушка из раздела «Что будет, если…»).
BY_DEPARTMENT_SQL = """
SELECT COALESCE(top_department, :none) AS top_name, COUNT(*) AS dismissed
FROM episodes
WHERE counts_in_turnover = 1
  AND substr(fire_date, 1, 7) BETWEEN :start AND :end
GROUP BY top_name
ORDER BY dismissed DESC, top_name
"""


def next_month(month: str) -> str:
    """Следующий месяц: «2026-10» → «2026-11», «2026-12» → «2027-01». (Пример к задаче 1.)"""
    year, number = month.split("-")
    year, number = int(year), int(number)
    if number == 12:  # после декабря — январь следующего года
        return f"{year + 1}-01"
    return f"{year}-{number + 1:02d}"


def months_between(start: str, end: str) -> list[str]:
    """Все месяцы от start до end включительно: («2026-11», «2027-01») → три месяца.

    Конец раньше начала → ValueError.
    """
    if start > end:  # ① шаг 1: начало позже конца — ошибка
        raise ValueError(f"начало периода {month_label(start)} позже конца {month_label(end)}")
    months = []  # ② шаг 2: пустой список — сюда будем складывать
    month = start  # шаг 3: начинаем с первого месяца
    while month <= end:  # шаг 4: пока не прошли конец
        months.append(month)  #   положить месяц в список
        month = next_month(month)  # ③ и шагнуть на следующий месяц (функция-пример выше)
    return months  # шаг 5: вернуть список


def average_ssch(values: list[float]) -> float:
    """Средняя ССЧ: сумма, делённая на количество. (Пример к задаче 2.)"""
    total = 0.0  # 1) копилка — пока пусто
    for value in values:  # 2) по каждому значению
        total += value  #    добавить его в копилку
    return total / len(values)  # 3) сумму разделить на количество


def with_shares(rows: list[tuple[str, int]]) -> list[tuple[str, int, float]]:
    """К каждому подразделению добавить долю в процентах от всех уволенных.

    [("ОП Северное", 3), ("ОП Восточное", 1)]
        → [("ОП Северное", 3, 75.0), ("ОП Восточное", 1, 25.0)]
    Пустой список — пустой список.
    """
    total = 0  # ① шаг 1: копилка — с какого числа она начинается?
    for _department, count in rows:
        total += count  #   добавить в копилку уволенных этого подразделения
    if total == 0:  # ② шаг 2: делить не на что — вернуть пустой список
        return []
    result = []  # шаг 3: новый список
    for department, count in rows:
        share = count / total * 100  # ③ доля в процентах: часть / целое × 100
        result.append((department, count, share))
    return result


@dataclass(frozen=True)
class PeriodTurnover:
    """Текучесть за период."""

    start: str  # «2026-07»
    end: str  # «2026-10»
    months: int  # сколько месяцев в периоде
    dismissed: int  # уволенные по причинам, входящим в текучесть
    ssch: float | None  # средняя ССЧ; None — не за все месяцы введена
    missing: tuple[str, ...]  # месяцы без ССЧ
    percent: float | None  # коэффициент, %; None — посчитать нельзя


def period_turnover(conn: sqlite3.Connection, start: str, end: str) -> PeriodTurnover:
    """Коэффициент текучести за период: уволенные / средняя ССЧ × 100."""
    months = months_between(start, end)
    ensure_ssch(conn)
    values = [get_ssch(conn, month) for month in months]
    missing = tuple(month for month, value in zip(months, values, strict=True) if value is None)
    ssch = None if missing else average_ssch(values)
    (dismissed,) = conn.execute(PERIOD_DISMISSED_SQL, {"start": start, "end": end}).fetchone()
    percent = dismissed / ssch * 100 if ssch else None
    return PeriodTurnover(
        start=start,
        end=end,
        months=len(months),
        dismissed=dismissed,
        ssch=ssch,
        missing=missing,
        percent=percent,
    )


def dismissed_by_department(
    conn: sqlite3.Connection, start: str, end: str
) -> list[tuple[str, int]]:
    """Уволенные (входит в текучесть) по подразделениям верхнего уровня, больше — выше."""
    params = {"start": start, "end": end, "none": NO_DEPARTMENT}
    return conn.execute(BY_DEPARTMENT_SQL, params).fetchall()


def period_label(start: str, end: str) -> str:
    """«07.2026–10.2026»; если месяц один — просто «10.2026»."""
    if start == end:
        return month_label(start)
    return f"{month_label(start)}–{month_label(end)}"


def describe_period(turnover: PeriodTurnover) -> str:
    """Итог одной строкой."""
    label = f"{period_label(turnover.start, turnover.end)} ({turnover.months} мес.)"
    dismissed = f"уволено (входит в текучесть) {turnover.dismissed}"
    if turnover.ssch is None:
        missing = ", ".join(month_label(month) for month in turnover.missing)
        return f"{label}: {dismissed}; нет ССЧ за {missing} — коэффициент не посчитать"
    return (
        f"{label}: средняя ССЧ {ru_number(turnover.ssch)} · {dismissed} · "
        f"коэффициент текучести {ru_number(turnover.percent, 2)} %"
    )


def describe_departments(rows: list[tuple[str, int, float]]) -> list[str]:
    """Строки таблицы: «ОП Северное — 45 (45,0 %)»."""
    return [f"{department} — {count} ({ru_number(share)} %)" for department, count, share in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Текучесть за период и по подразделениям")
    parser.add_argument("start", help="первый месяц, мм.гггг: 07.2026")
    parser.add_argument("end", nargs="?", help="последний месяц (по умолчанию = первый)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    try:
        start = parse_month(args.start)
        end = parse_month(args.end) if args.end else start
        conn = connect(args.db)
        turnover = period_turnover(conn, start, end)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error

    print(describe_period(turnover))
    lines = describe_departments(with_shares(dismissed_by_department(conn, start, end)))
    if lines:
        print("По подразделениям (уволено, доля от всех уволенных):")
        for line in lines:
            print(f"  {line}")
    conn.close()


if __name__ == "__main__":
    main()
