"""Шаблон «Что выгрузить из 1С»: какие колонки нужны приложению и как они могут называться.

Создать файл: uv run python -m hr_pulse.ingest.template [путь.xlsx]
Шаблон строится из TEMPLATE в fields.py — поменяли поля там, шаблон обновится сам.
"""

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from hr_pulse.core.fields import TEMPLATE, FieldKind

DEFAULT_PATH = Path("Что_выгрузить_из_1С.xlsx")
HEADER = ("Поле", "Обязательное", "Персональные данные", "Формат", "Как может называться в 1С")
KIND_FORMAT = {
    FieldKind.TEXT: "текст",
    FieldKind.DATE: "дд.мм.гггг",
    FieldKind.SNILS: "123-456-789 01",
}


def template_rows() -> list[tuple[str, str, str, str, str]]:
    """Строки шаблона: по одной на поле, в порядке TEMPLATE."""
    rows = []
    for spec in TEMPLATE:
        rows.append(
            (
                spec.title,
                "да" if spec.required else "нет",
                "да — 152-ФЗ" if spec.personal_data else "нет",
                KIND_FORMAT[spec.kind],
                ", ".join(spec.synonyms) or "—",
            )
        )
    return rows


def write_template(path: Path) -> None:
    """Записать шаблон в Excel: заголовок жирным, ширина колонок по содержимому."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Что выгрузить"
    ws.append(HEADER)
    for row in template_rows():
        ws.append(row)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for column, width in zip("ABCDE", (32, 14, 20, 16, 70), strict=True):
        ws.column_dimensions[column].width = width
    wb.save(path)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    write_template(target)
    print(f"Шаблон записан: {target.resolve()}")
