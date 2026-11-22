"""Приёмочный тест: сверить HR Pulse с вашим собственным отчётом о текучести.

Команды:
  uv run python -m hr_pulse.quality.acceptance эталон.xlsx            — сверка
  uv run python -m hr_pulse.quality.acceptance --template эталон.xlsx — пустой бланк
  uv run python -m hr_pulse.quality.acceptance --details 09.2026 "ОП Северное"
                                                  — из чего сложилось число уволенных

Эталон — Excel-таблица, которую вы заполняете цифрами из своего отчёта:
  Месяц | Подразделение | Уволено | ССЧ | Кт
Подразделение «Итого» — организация целиком. ССЧ и Кт можно не заполнять.

Допуски: уволенные — точно; ССЧ — 3 % (у подразделений программа считает среднюю
списочную, а не ССЧ, шаг 6.2); Кт — 0,5 п.п. Печатает только числа и названия
подразделений и причин — без ФИО, СНИЛС и табельных номеров.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from hr_pulse.analytics.departments import average_headcount
from hr_pulse.analytics.turnover import NO_DEPARTMENT, dismissed_by_department
from hr_pulse.core.formats_1c import is_blank
from hr_pulse.db.ssch import month_label, parse_month, ru_number, turnover_for_month
from hr_pulse.db.ssch_file import cell_to_month
from hr_pulse.db.storage import DEFAULT_DB, connect

ORG = "Итого"
ORG_NAMES = {"итого", "всего", "организация", "по организации"}

DISMISSED, SSCH, RATE = "Уволено", "ССЧ", "Кт"
SSCH_SHARE = 0.03  # ССЧ: допуск 3 % от числа в отчёте
RATE_POINTS = 0.5  # Кт: допуск 0,5 п.п.
DIGITS = {DISMISSED: 0, SSCH: 1, RATE: 2}

# Как могут называться колонки в вашем отчёте (сравниваем маленькими буквами, по началу)
HEADERS = {
    "month": ("месяц",),
    "department": ("подразделение", "оп"),
    DISMISSED: ("уволено", "уволенные", "уволен"),
    SSCH: ("ссч", "среднесписочн"),
    RATE: ("кт", "коэффициент", "текучесть"),
}
REQUIRED = ("month", "department", DISMISSED)

# Увольнения месяца в подразделении — по причинам (для --details)
DETAILS_SQL = """
SELECT COALESCE(fire_reason, '(причина не указана)') AS reason,
       counts_in_turnover, COUNT(*) AS dismissed
FROM episodes
WHERE substr(fire_date, 1, 7) = :month
  AND COALESCE(top_department, :none) = :department
GROUP BY reason, counts_in_turnover
ORDER BY counts_in_turnover DESC, dismissed DESC, reason
"""


@dataclass(frozen=True)
class Check:
    """Одна проверка: одно число из отчёта против числа HR Pulse."""

    month: str  # «2026-09»
    department: str  # «ОП Северное» или «Итого»
    metric: str  # «Уволено», «ССЧ», «Кт»
    ours: float | None  # HR Pulse; None — посчитать нечем
    theirs: float  # из вашего отчёта
    ok: bool


# ---------- чтение эталона ----------


def match_header(text: str) -> str | None:
    """Какая это колонка эталона: «Уволено, чел.» → «Уволено»; не наша — None."""
    words = text.strip().lower().replace(",", " ").split()
    if not words:
        return None
    first = words[0]  # «Уволено, чел.» → «уволено»
    for key, names in HEADERS.items():
        # короткие названия («оп», «кт») — только целым словом, длинные — и по началу
        if any(first == name or (len(name) > 3 and first.startswith(name)) for name in names):
            return key
    return None


def find_header(raw: pd.DataFrame) -> tuple[int, dict[str, int]]:
    """Строка заголовков (с 0) и номера колонок: {"month": 0, "department": 1, …}."""
    for row_index, row in enumerate(raw.itertuples(index=False)):
        columns: dict[str, int] = {}
        for col, cell in enumerate(row):
            key = None if is_blank(cell) else match_header(str(cell))
            if key and key not in columns:
                columns[key] = col
        if all(key in columns for key in REQUIRED):
            return row_index, columns
    raise ValueError(
        "не нашёл строку заголовков: нужны колонки «Месяц», «Подразделение», «Уволено»"
    )


def parse_number(value: object) -> float | None:
    """«549,5», «1 545», «6,36 %» → число; пусто — None; не число — ValueError."""
    if is_blank(value):
        return None
    text = str(value).replace("\xa0", "").replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(text)
    except ValueError as error:
        raise ValueError(f"не число: {value!r}") from error


@dataclass(frozen=True)
class Expected:
    """Строка эталона."""

    row: int  # номер строки Excel
    month: str
    department: str  # ORG — организация
    values: dict[str, float]  # {"Уволено": 7, "ССЧ": 255.0, "Кт": 2.75} — только заполненные


def read_expected(path: Path) -> tuple[list[Expected], list[str]]:
    """Строки эталона и ошибки «строка N: …». Кт в долях (0,0636) переводит в проценты."""
    raw = pd.read_excel(path, engine="calamine", header=None, dtype=str)
    header, columns = find_header(raw)
    rows: list[Expected] = []
    errors: list[str] = []
    for number, row in enumerate(raw.iloc[header + 1 :].itertuples(index=False), start=header + 2):
        cells = {key: row[col] for key, col in columns.items()}
        if all(is_blank(value) for value in cells.values()):
            continue
        try:
            month = cell_to_month(str(cells["month"]))
            department = str(cells["department"]).strip()
            if department.lower() in ORG_NAMES:
                department = ORG
            values = {}
            for metric in (DISMISSED, SSCH, RATE):
                value = parse_number(cells.get(metric))
                if value is not None:
                    values[metric] = value
            if DISMISSED not in values:
                raise ValueError("не указано число уволенных")
            rows.append(Expected(number, month, department, values))
        except ValueError as error:
            errors.append(f"строка {number}: {error}")
    rates = [row.values[RATE] for row in rows if RATE in row.values]
    if rates and max(rates) <= 1:  # Excel хранит «6,36 %» как 0,0636
        rows = [as_percent(row) for row in rows]
    return rows, errors


def as_percent(row: Expected) -> Expected:
    """Кт из доли в проценты: 0,0636 → 6,36."""
    if RATE not in row.values:
        return row
    values = {**row.values, RATE: row.values[RATE] * 100}
    return Expected(row.row, row.month, row.department, values)


# ---------- сверка ----------


def is_match(ours: float | None, theirs: float, tolerance: float) -> bool:
    """Совпадает ли число HR Pulse с числом из отчёта с учётом допуска.
    HR Pulse не смог посчитать (None) — не совпадает.
    """
    if ours is None:
        return False
    difference = round(abs(theirs - ours), 6)
    return difference <= tolerance  # шаг 3: в пределах допуска?


def tolerance_for(metric: str, theirs: float) -> float:
    """Допуск: уволенные — 0; ССЧ — 3 % от числа отчёта; Кт — 0,5 п.п."""
    if metric == SSCH:
        return round(theirs * SSCH_SHARE, 6)
    if metric == RATE:
        return RATE_POINTS
    return 0


def our_values(conn: sqlite3.Connection, month: str, department: str) -> dict[str, float | None]:
    """Числа HR Pulse за месяц: для «Итого» — с официальной ССЧ, для ОП — средняя списочная."""
    headcount = average_headcount(conn, month, month)
    if department == ORG:
        turnover = turnover_for_month(conn, month)
        ssch = turnover.ssch if turnover.ssch is not None else sum(headcount.values()) or None
        dismissed = turnover.dismissed
    else:
        dismissed = dict(dismissed_by_department(conn, month, month)).get(department, 0)
        ssch = headcount.get(department)
    rate = dismissed / ssch * 100 if ssch else None
    return {DISMISSED: dismissed, SSCH: ssch, RATE: rate}


def compare(conn: sqlite3.Connection, expected: list[Expected]) -> list[Check]:
    """Все проверки по эталону."""
    checks = []
    for row in expected:
        ours = our_values(conn, row.month, row.department)
        for metric, theirs in row.values.items():
            ok = is_match(ours[metric], theirs, tolerance_for(metric, theirs))
            checks.append(Check(row.month, row.department, metric, ours[metric], theirs, ok))
    return checks


def summary(checks: list[Check]) -> str:
    """Итог сверки одной строкой."""
    if not checks:
        return "В эталоне нет ни одной проверки"
    passed = 0
    failed = 0
    for check in checks:
        if check.ok:
            passed += 1
        else:
            failed += 1
    if failed == 0:
        return f"Совпало {passed} из {len(checks)} — приёмка пройдена"
    return f"Совпало {passed} из {len(checks)}, расхождений: {failed}"


def number(value: float | None, metric: str) -> str:
    """Число для экрана; None — «нет»."""
    if value is None:
        return "нет"
    return ru_number(value, DIGITS[metric]) if DIGITS[metric] else str(round(value))


def describe_check(check: Check) -> str:
    """«✗ 09.2026 · ОП Северное · Уволено: отчёт 9, HR Pulse 7»."""
    mark = "✓" if check.ok else "✗"
    place = f"{month_label(check.month)} · {check.department} · {check.metric}"
    return (
        f"{mark} {place}: отчёт {number(check.theirs, check.metric)}, "
        f"HR Pulse {number(check.ours, check.metric)}"
    )


def details(conn: sqlite3.Connection, month: str, department: str) -> list[str]:
    """Увольнения месяца в подразделении по причинам: «Входит» и «Не входит» отдельно."""
    params = {"month": month, "department": department, "none": NO_DEPARTMENT}
    lines = []
    for reason, counts, dismissed in conn.execute(DETAILS_SQL, params):
        status = {1: "входит", 0: "не входит"}.get(counts, "не классифицирована")
        lines.append(f"{reason} — {dismissed} ({status})")
    return lines


def write_template(path: Path) -> None:
    """Пустой бланк эталона."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Эталон"
    ws.append(["Заполните строки ниже цифрами из своего отчёта. «Итого» — вся организация."])
    ws.append([])
    ws.append(["Месяц", "Подразделение", "Уволено", "ССЧ", "Кт"])
    for column, width in zip("ABCDE", (10, 28, 10, 10, 8), strict=True):
        ws.column_dimensions[column].width = width
    wb.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Приёмочный тест: HR Pulse против вашего отчёта")
    parser.add_argument("file", nargs="?", type=Path, help="эталон .xlsx")
    parser.add_argument("--template", action="store_true", help="записать пустой бланк в file")
    parser.add_argument(
        "--details",
        nargs=2,
        metavar=("МЕСЯЦ", "ПОДРАЗДЕЛЕНИЕ"),
        help="увольнения месяца в подразделении по причинам",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    if args.details:
        month_text, department = args.details
        try:
            month = parse_month(month_text)
        except ValueError as error:
            parser.error(str(error))
        conn = connect(args.db)
        lines = details(conn, month, department)
        conn.close()
        print(f"{month_label(month)} · {department}: уволенные по причинам")
        for line in lines or ["увольнений нет — проверьте название подразделения"]:
            print(f"  {line}")
        return
    if args.file is None:
        parser.error("укажите файл эталона")
    if args.template:
        write_template(args.file)
        print(f"Бланк записан: {args.file.name}")
        return

    try:
        expected, errors = read_expected(args.file)
    except (OSError, ValueError) as error:
        print(f"Не получилось прочитать {args.file.name}: {error}")
        raise SystemExit(1) from error
    for line in errors:
        print(f"Пропущена {line}")

    conn = connect(args.db)
    checks = compare(conn, expected)
    conn.close()
    for check in checks:
        print(describe_check(check))
    print()
    print(summary(checks))
    if not all(check.ok for check in checks):
        raise SystemExit(1)  # код 1 — «приёмка не пройдена»


if __name__ == "__main__":
    main()
