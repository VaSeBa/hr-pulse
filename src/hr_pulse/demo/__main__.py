"""Создать демо-выгрузки: uv run python -m hr_pulse.demo [папка]

По умолчанию файлы появляются в папке demo_data/ в корне проекта.
Файлы .xlsx не попадают в Git (правило в .gitignore) — их всегда можно создать заново.
"""

import sys
from pathlib import Path

from hr_pulse.demo.dirty import spoil_employees
from hr_pulse.demo.export_1c import (
    write_employees_report,
    write_reasons_reference,
    write_reasons_report,
)
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.demo.monthly import OCTOBER_END, october_rows
from hr_pulse.demo.ssch_file import write_ssch_report


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo_data")
    folder.mkdir(parents=True, exist_ok=True)

    config = GeneratorConfig()
    rows = FakeCompany(config).generate()
    period = f"01.01.2024 - {config.end.strftime('%d.%m.%Y')}"

    write_employees_report(rows, folder / "Сотрудники_демо.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, folder / "Причины_увольнений_демо.xlsx", period=period)
    write_reasons_reference(folder / "Справочник_причин_демо.xlsx")

    october = october_rows(rows)  # «следующий месяц» — для догрузки в базу
    write_employees_report(
        october, folder / "Сотрудники_октябрь_демо.xlsx", mislabel_fire_date=True
    )
    october_period = f"01.01.2024 - {OCTOBER_END.strftime('%d.%m.%Y')}"
    write_reasons_report(
        october, folder / "Причины_увольнений_октябрь_демо.xlsx", period=october_period
    )

    # ССЧ «от бухгалтерии» за 2024 — июнь 2026 (июль–октябрь 2026 вводили руками в 5.4 и 6.1)
    write_ssch_report(october, folder / "ССЧ_демо.xlsx", "2024-01", "2026-06")

    dirty = folder / "Сотрудники_с_ошибками_демо.xlsx"  # для проверки качества данных
    write_employees_report(rows, dirty, mislabel_fire_date=True)
    spoil_employees(dirty)

    print(f"Готово: {len(rows)} эпизодов. Файлы в папке {folder.resolve()}")


if __name__ == "__main__":
    main()
