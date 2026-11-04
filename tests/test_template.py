"""Тесты шага 3.1: шаблон «Что выгрузить из 1С»."""

from openpyxl import load_workbook

from hr_pulse.core.fields import TEMPLATE
from hr_pulse.ingest.template import HEADER, template_rows, write_template


def test_one_row_per_field():
    assert len(template_rows()) == len(TEMPLATE)


def test_snils_marked_as_personal_data():
    snils = next(row for row in template_rows() if row[0] == "СНИЛС")
    assert snils[1] == "да"  # обязательное
    assert snils[2].startswith("да")  # ПДн


def test_written_file_has_header_and_rows(tmp_path):
    path = tmp_path / "template.xlsx"
    write_template(path)
    ws = load_workbook(path).active
    assert tuple(cell.value for cell in ws[1]) == HEADER
    assert ws.max_row == len(TEMPLATE) + 1
