"""Посмотреть структуру выгрузки: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx

Печатает только структуру — где заголовок, число строк, названия колонок,
их заполненность и отметку «даты». Сами данные (ФИО, СНИЛС) на экран не выводятся,
поэтому команду можно безопасно запускать и на реальных выгрузках.
"""

import sys
from pathlib import Path

from hr_pulse.ingest.convert import date_share
from hr_pulse.ingest.reader import describe, read_1c_table

DATE_MARK_SHARE = 0.9  # колонку считаем датами, если ≥ 90% значений — даты


def main() -> None:
    if len(sys.argv) != 2:
        print("Использование: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx")
        sys.exit(1)

    table = read_1c_table(Path(sys.argv[1]))
    print(describe(table))
    print("Колонки:")
    for number, name in enumerate(table.frame.columns, start=1):
        column = table.frame[name]
        filled = column.notna().mean() * 100
        mark = "  [даты]" if date_share(column) >= DATE_MARK_SHARE else ""
        print(f"  {number:2}. {name}  (заполнено {filled:.0f}%){mark}")


if __name__ == "__main__":
    main()
