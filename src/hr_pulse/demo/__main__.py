"""Создать демо-выгрузки: uv run python -m hr_pulse.demo [папка]

По умолчанию файлы появляются в папке demo_data/ в корне проекта.
Файлы .xlsx не попадают в Git (правило в .gitignore) — их всегда можно создать заново.
"""

import sys
from pathlib import Path

from hr_pulse.demo.export_1c import (
    write_employees_report,
    write_reasons_reference,
    write_reasons_report,
)
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo_data")
    folder.mkdir(parents=True, exist_ok=True)

    config = GeneratorConfig()
    rows = FakeCompany(config).generate()
    period = f"01.01.2024 - {config.end.strftime('%d.%m.%Y')}"

    write_employees_report(rows, folder / "Сотрудники_демо.xlsx", mislabel_fire_date=True)
    write_reasons_report(rows, folder / "Причины_увольнений_демо.xlsx", period=period)
    write_reasons_reference(folder / "Справочник_причин_демо.xlsx")

    print(f"Готово: {len(rows)} эпизодов. Файлы в папке {folder.resolve()}")


if __name__ == "__main__":
    main()
