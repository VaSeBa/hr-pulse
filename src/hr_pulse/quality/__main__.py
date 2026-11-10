"""Проверить качество выгрузки: uv run python -m hr_pulse.quality файл.xlsx [--fire-date "…"]

Печатает найденные проблемы и номера строк Excel — без ФИО, СНИЛС и табельных номеров.
"""

import argparse
from pathlib import Path

from hr_pulse.core.fields import Field, get_spec
from hr_pulse.ingest.mapping import apply_mapping, map_columns
from hr_pulse.ingest.reader import read_1c_table
from hr_pulse.quality.checks import describe_issues, run_checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверить качество выгрузки сотрудников")
    parser.add_argument("employees", type=Path, help="выгрузка «Личные данные сотрудников»")
    parser.add_argument("--fire-date", help="колонка с датой увольнения, если не узналась сама")
    args = parser.parse_args()

    table = read_1c_table(args.employees)
    overrides = {args.fire_date: Field.FIRE_DATE} if args.fire_date else None
    mapping = map_columns(table.frame, overrides)
    frame = apply_mapping(table.frame, mapping)

    for missing in mapping.missing:
        print(f"Не найдено обязательное поле: {get_spec(missing).title} — его не проверяем")
    for line in describe_issues(run_checks(frame, table.source_rows)):
        print(line)


if __name__ == "__main__":
    main()
