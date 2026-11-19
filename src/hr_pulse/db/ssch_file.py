"""ССЧ из Excel-файла: сразу за много месяцев.

Команда:  uv run python -m hr_pulse.db.ssch_file demo_data/ССЧ_демо.xlsx

В файле должна быть строка заголовков с колонками «Месяц» и «ССЧ»
(или «Среднесписочная …»); над ней может быть шапка отчёта. Месяц — «01.2026»
или дата Excel (01.01.2026). Плохие строки не загружаются: команда печатает
номер строки Excel и что не так — и загружает остальные.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hr_pulse.core.formats_1c import is_blank
from hr_pulse.db.ssch import (
    get_ssch,
    month_label,
    parse_month,
    # parse_ssch нужен в задаче 1. Пока задача не решена, ruff считает его лишним;
    # пометка noqa просит не ругаться. После решения её можно убрать.
    parse_ssch,  # noqa: F401
    ru_number,
    set_ssch,
)
from hr_pulse.db.storage import DEFAULT_DB, connect


def is_ssch_header(text: str) -> bool:
    """Заголовок колонки ССЧ: «ССЧ», «Среднесписочная численность»…"""
    text = text.strip().lower()
    return text.startswith("сс") or text.startswith("среднесписочн")


def find_columns(raw: pd.DataFrame) -> tuple[int, int, int]:
    """Номер строки заголовков (с 0), колонки «Месяц» и колонки ССЧ. Нет — ValueError."""
    for row_index, row in enumerate(raw.itertuples(index=False)):
        cells = ["" if is_blank(cell) else str(cell) for cell in row]
        months = [i for i, cell in enumerate(cells) if cell.strip().lower() == "месяц"]
        values = [i for i, cell in enumerate(cells) if is_ssch_header(cell)]
        if months and values:
            return row_index, months[0], values[0]
    raise ValueError("не нашёл строку заголовков с колонками «Месяц» и «ССЧ»")


def read_table(path: Path) -> tuple[list[tuple[str, str]], int]:
    """Пары «месяц, ССЧ» текстом и номер строки Excel, с которой они начинаются.
    Пустые строки остаются (их отсеет read_ssch_rows), чтобы номера строк совпадали с Excel.
    """
    raw = pd.read_excel(path, engine="calamine", header=None, dtype=str)
    header, month_col, value_col = find_columns(raw)
    table = []
    for row in raw.iloc[header + 1 :].itertuples(index=False):
        month, value = row[month_col], row[value_col]
        table.append(("" if is_blank(month) else month, "" if is_blank(value) else value))
    return table, header + 2  # номер в Excel первой строки данных (с 1)


def cell_to_month(text: str) -> str:
    """Месяц из ячейки: «10.2026» → «2026-10»; дата Excel «2026-10-01 00:00:00» → «2026-10»."""
    text = text.strip()
    if len(text) >= 7 and text[:4].isdigit() and text[4] == "-":  # дата: «2026-10-01…»
        return parse_month(f"{text[5:7]}.{text[:4]}")  # та же проверка, что и для «10.2026»
    return parse_month(text)


def good_numbers(texts: list[str]) -> tuple[list[int], list[str]]:
    """Числа из списка текстов — и то, что числом не оказалось."""
    numbers = []  # хорошие
    bad = []  # плохие
    for text in texts:
        try:  # пробуем…
            numbers.append(int(text))
        except ValueError:  # …не вышло — откладываем в «плохие» и идём дальше
            bad.append(text)
    return numbers, bad


def read_ssch_rows(
    table: list[tuple[str, str]], first_row: int = 2
) -> tuple[list[tuple[str, float]], list[str]]:
    """Пары текстов → хорошие пары («2026-10», 549.5) и ошибки «строка 5: …».
    first_row — номер строки Excel для первой пары. Пустые строки пропускаются молча.
    """
    good = []
    errors = []
    for number, row in enumerate(table, start=first_row):  # номер строки в Excel
        month_text, value_text = row
        if not month_text and not value_text:
            continue
        try:
            month = cell_to_month(month_text)
            value = parse_ssch(value_text)
            good.append((month, value))  # шаг 3: всё получилось — в хорошие
        except ValueError as error:
            errors.append(f"строка {number}: {error}")  # шаг 4: не вышло — в ошибки
    return good, errors


@dataclass(frozen=True)
class SschImport:
    """Итог загрузки ССЧ из файла."""

    added: int  # новых месяцев
    same: int  # такое значение уже было
    changed: tuple[str, ...]  # «07.2026: 561,0 → 562,3»


def import_ssch(conn: sqlite3.Connection, pairs: list[tuple[str, float]]) -> SschImport:
    """Записать месяцы в базу. Уже введённые с другим значением — заменяются, и это видно."""
    added = same = 0
    changed = []
    for month, value in pairs:
        before = get_ssch(conn, month)
        if before == value:
            same += 1
            continue
        set_ssch(conn, month, value)
        if before is None:
            added += 1
        else:
            changed.append(f"{month_label(month)}: {ru_number(before)} → {ru_number(value)}")
    return SschImport(added=added, same=same, changed=tuple(changed))


def main() -> None:
    parser = argparse.ArgumentParser(description="ССЧ по месяцам из Excel-файла")
    parser.add_argument("file", type=Path, help="файл .xlsx с колонками «Месяц» и «ССЧ»")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    args = parser.parse_args()

    try:
        table, first_row = read_table(args.file)
    except (OSError, ValueError) as error:
        print(f"Не получилось прочитать {args.file.name}: {error}")
        raise SystemExit(1) from error

    good, errors = read_ssch_rows(table, first_row)
    conn = connect(args.db)
    result = import_ssch(conn, good)
    conn.close()

    print(f"Файл {args.file.name}: месяцев с ССЧ — {len(good)}")
    print(
        f"Новых: {result.added} · без изменений: {result.same} · исправлено: {len(result.changed)}"
    )
    for line in result.changed:
        print(f"  {line}")
    if errors:
        print(f"Не загружено строк: {len(errors)}")
        for line in errors:
            print(f"  {line}")


if __name__ == "__main__":
    main()
