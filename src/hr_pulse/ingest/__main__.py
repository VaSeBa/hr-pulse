"""Посмотреть структуру выгрузки: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx

Печатает только структуру — номер строки заголовков, число строк и названия колонок.
Сами данные (ФИО, СНИЛС) на экран не выводятся, поэтому команду можно
безопасно запускать и на реальных выгрузках.
"""

import sys
from pathlib import Path

from hr_pulse.ingest.reader import describe, read_1c_table


def main() -> None:
    if len(sys.argv) != 2:
        print("Использование: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx")
        sys.exit(1)

    table = read_1c_table(Path(sys.argv[1]))
    print(describe(table))
    print("Колонки:")
    for number, name in enumerate(table.frame.columns, start=1):
        filled = table.frame[name].notna().mean() * 100
        print(f"  {number:2}. {name}  (заполнено {filled:.0f}%)")


if __name__ == "__main__":
    main()
