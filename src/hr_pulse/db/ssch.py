"""ССЧ — среднесписочная численность по месяцам, которую вводит человек.

Команда:  uv run python -m hr_pulse.db.ssch 10.2026 549,5   — ввести (или исправить) ССЧ
          uv run python -m hr_pulse.db.ssch 10.2026         — текучесть за месяц
          uv run python -m hr_pulse.db.ssch                 — все введённые месяцы


ССЧ считает бухгалтерия или отдел кадров по своим правилам (совместители,
декрет, неполный день). Программа её не пересчитывает — её вводят руками
по каждому месяцу, как решили в начале курса. С ССЧ появляется первый
показатель: коэффициент текучести за месяц.

    Кт = уволенные по причинам, входящим в текучесть / ССЧ × 100 %
"""

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hr_pulse.core.formats_1c import is_blank
from hr_pulse.db.storage import DEFAULT_DB, connect

MONTH_HINT = "месяц пишется так: 10.2026"

SSCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS ssch (
    month       TEXT PRIMARY KEY,  -- «2026-10»: один месяц — одно значение
    value       REAL NOT NULL,     -- ССЧ, может быть дробной: 545.3
    entered_at  TEXT NOT NULL      -- когда ввели: «2026-11-15 20:30»
);
"""

# Уволенные за месяц по причинам, которые входят в текучесть (шаг 3.3).
# substr(fire_date, 1, 7) — первые 7 символов даты: «2026-10-15» → «2026-10».
DISMISSED_SQL = """
SELECT COUNT(*)
FROM episodes
WHERE counts_in_turnover = 1
  AND substr(fire_date, 1, 7) = :month
"""


def month_label(month: str) -> str:
    """Месяц для человека: «2026-10» → «10.2026». (Разобранный пример к задаче 1.)"""
    year, number = month.split("-")  # 1) разрезать по «-»: ["2026", "10"]
    return f"{number}.{year}"  # 2) собрать в другом порядке


def parse_month(text: str) -> str:
    """Месяц от человека: «10.2026» → «2026-10». Неверный месяц → ValueError."""
    text = text.strip()
    if text.count(".") != 1:  # шаг 1: ровно одна точка
        raise ValueError(f"{MONTH_HINT}, а не {text!r}")
    number, year = text.split(".")  # шаг 2: разрезать по точке — как в month_label
    if not (number.isdigit() and year.isdigit()):  # шаг 3: обе части — цифры
        raise ValueError(f"{MONTH_HINT}, а не {text!r}")
    if not 1 <= int(number) <= 12 or len(year) != 4:
        raise ValueError(f"{MONTH_HINT}, а не {text!r}")
    return f"{year}-{int(number):02d}"


def parse_ssch(value: object) -> float:
    """ССЧ, как её пишут в Excel: «1 545,3» → 1545.3. Не число или не больше нуля → ValueError."""
    if is_blank(value):  # шаг 1: пусто — ошибка
        raise ValueError("ССЧ не указана")
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:  # шаг 3: превратить в число
        number = float(text)  # готово: float — «дробное число»; не число → ValueError
    except ValueError as error:
        raise ValueError(f"ССЧ — это число, а не {value!r}") from error
    if number <= 0:  # шаг 4: ноль или меньше — ошибка
        raise ValueError("ССЧ должна быть больше нуля")
    return number


def ru_number(value: float, digits: int = 1) -> str:
    """Число по-русски, с запятой: 545.3 → «545,3»."""
    return f"{value:.{digits}f}".replace(".", ",")


def ensure_ssch(conn: sqlite3.Connection) -> None:
    """Создать таблицу ССЧ, если её ещё нет."""
    conn.executescript(SSCH_SCHEMA)


def set_ssch(
    conn: sqlite3.Connection, month: str, value: float, now: datetime | None = None
) -> float | None:
    """Записать ССЧ за месяц (или заменить). Возвращает прежнее значение или None."""
    ensure_ssch(conn)
    before = get_ssch(conn, month)
    now = now or datetime.now()
    with conn:
        conn.execute(
            "INSERT INTO ssch (month, value, entered_at) VALUES (?, ?, ?) "
            "ON CONFLICT(month) DO UPDATE SET value = excluded.value, "
            "entered_at = excluded.entered_at",
            (month, value, now.strftime("%Y-%m-%d %H:%M")),
        )
    return before


def get_ssch(conn: sqlite3.Connection, month: str) -> float | None:
    """ССЧ за месяц; не введена — None."""
    ensure_ssch(conn)
    row = conn.execute("SELECT value FROM ssch WHERE month = ?", (month,)).fetchone()
    return row[0] if row else None


def list_ssch(conn: sqlite3.Connection) -> list[tuple[str, float]]:
    """Все введённые месяцы по порядку: [("2026-09", 557.0), ("2026-10", 549.5)]."""
    ensure_ssch(conn)
    return conn.execute("SELECT month, value FROM ssch ORDER BY month").fetchall()


@dataclass(frozen=True)
class Turnover:
    """Текучесть за месяц."""

    month: str  # «2026-10»
    dismissed: int  # уволенные по причинам, входящим в текучесть
    ssch: float | None  # ССЧ; None — не введена
    percent: float | None  # коэффициент текучести, %; None — посчитать нельзя


def turnover_for_month(conn: sqlite3.Connection, month: str) -> Turnover:
    """Коэффициент текучести за месяц: уволенные (входит в текучесть) / ССЧ × 100."""
    (dismissed,) = conn.execute(DISMISSED_SQL, {"month": month}).fetchone()
    ssch = get_ssch(conn, month)
    percent = dismissed / ssch * 100 if ssch else None
    return Turnover(month=month, dismissed=dismissed, ssch=ssch, percent=percent)


def describe_turnover(turnover: Turnover) -> str:
    """Итог одной строкой."""
    label = month_label(turnover.month)
    if turnover.ssch is None:
        return (
            f"{label}: уволено (входит в текучесть) {turnover.dismissed}; "
            "ССЧ не введена — коэффициент не посчитать"
        )
    return (
        f"{label}: ССЧ {ru_number(turnover.ssch)} · "
        f"уволено (входит в текучесть) {turnover.dismissed} · "
        f"коэффициент текучести {ru_number(turnover.percent, 2)} %"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ССЧ по месяцам и коэффициент текучести")
    parser.add_argument("month", nargs="?", help="месяц, мм.гггг: 10.2026")
    parser.add_argument("value", nargs="?", help="ССЧ за месяц: 549,5")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    conn = connect(args.db)
    if args.month is None:  # без аргументов — список введённого
        rows = list_ssch(conn)
        for month, value in rows:
            print(f"{month_label(month)} — {ru_number(value)}")
        if not rows:
            print("ССЧ ещё не вводили. Пример: uv run python -m hr_pulse.db.ssch 10.2026 549,5")
        return

    try:
        month = parse_month(args.month)
        if args.value is not None:
            before = set_ssch(conn, month, parse_ssch(args.value))
            if before is not None:
                print(f"ССЧ за {month_label(month)} исправлена: было {ru_number(before)}")
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error

    print(describe_turnover(turnover_for_month(conn, month)))
    conn.close()


if __name__ == "__main__":
    main()
