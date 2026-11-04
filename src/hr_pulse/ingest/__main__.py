"""Посмотреть структуру выгрузки: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx

Печатает только структуру — где заголовок, число строк, сверку с «Количество»
из шапки, названия колонок, их заполненность, отметку «даты» и какое поле шаблона
узнано в каждой колонке. Сами данные (ФИО, СНИЛС) на экран не выводятся, поэтому
команду можно безопасно запускать и на реальных выгрузках.
"""

import sys
from pathlib import Path

from hr_pulse.core.fields import get_spec
from hr_pulse.ingest.checks import check_table, describe_check
from hr_pulse.ingest.convert import date_share
from hr_pulse.ingest.mapping import map_columns
from hr_pulse.ingest.reader import describe, read_1c_table

DATE_MARK_SHARE = 0.9  # колонку считаем датами, если ≥ 90% значений — даты


def main() -> None:
    if len(sys.argv) != 2:
        print("Использование: uv run python -m hr_pulse.ingest путь/к/файлу.xlsx")
        sys.exit(1)

    table = read_1c_table(Path(sys.argv[1]))
    mapping = map_columns(table.frame)
    print(describe(table))
    print("Сверка с шапкой:", describe_check(check_table(table)))
    print("Колонки:")
    for number, name in enumerate(table.frame.columns, start=1):
        column = table.frame[name]
        filled = column.notna().mean() * 100
        mark = "  [даты]" if date_share(column) >= DATE_MARK_SHARE else ""
        if name in mapping.fields:
            target = f"→ {get_spec(mapping.fields[name]).title}"
        elif name in mapping.duplicates:
            target = "→ (поле уже занято другой колонкой)"
        else:
            target = "→ не используется"
        print(f"  {number:2}. {name}  (заполнено {filled:.0f}%){mark}  {target}")

    for missing in mapping.missing:
        print(f"Не найдено обязательное поле: {get_spec(missing).title}")
        for name in mapping.suggestions.get(missing, []):
            print(f"   может быть, это колонка «{name}»? (в ней даты)")


if __name__ == "__main__":
    main()
