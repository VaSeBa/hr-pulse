"""Отчёт о качестве данных в Excel: сводка по проблемам и список всех строк.

В отчёте только номера строк исходного файла, названия проблем и ссылки «открыть»,
которые ведут прямо на строку в выгрузке. Ни ФИО, ни СНИЛС — отчёт можно
переслать коллеге, который будет исправлять данные в 1С.
"""

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from hr_pulse.core.formats_1c import ru_date
from hr_pulse.quality.checks import Issue, Severity, short_rows

FILLS = {
    Severity.ERROR: PatternFill("solid", fgColor="F8D7D0"),  # светло-красный
    Severity.WARNING: PatternFill("solid", fgColor="FBF0D0"),  # светло-жёлтый
}
SUMMARY_HEADER = ("Серьёзность", "Проблема", "Строк", "Первые строки Excel")
ROWS_HEADER = ("Строка Excel", "Серьёзность", "Проблема", "Открыть")


def issue_rows(issues: list[Issue]) -> list[tuple[int, Severity, str]]:
    """Все проблемы «по строке»: (номер строки, серьёзность, проблема), по возрастанию строк."""
    result = []
    for issue in issues:
        for row in issue.rows:
            result.append((row, issue.severity, issue.title))
    result.sort()
    return result


def style_header(ws: Worksheet, widths: tuple[int, ...]) -> None:
    """Заголовок жирным, закрепить первую строку, фильтр, ширина колонок."""
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"  # первая строка не уезжает при прокрутке
    ws.auto_filter.ref = ws.dimensions  # фильтр на всю таблицу
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=index).column_letter].width = width


def write_quality_report(
    issues: list[Issue],
    path: Path,
    *,
    source: Path,
    sheet: str,
    today: date | None = None,
) -> None:
    """Записать отчёт: лист «Сводка» и лист «Строки» со ссылками на исходный файл."""
    today = today or date.today()
    wb = Workbook()

    summary = wb.active
    summary.title = "Сводка"
    summary.append(SUMMARY_HEADER)
    for issue in issues:
        summary.append((str(issue.severity), issue.title, len(issue.rows), short_rows(issue.rows)))
        for cell in summary[summary.max_row]:
            cell.fill = FILLS[issue.severity]
    style_header(summary, (16, 60, 8, 40))
    summary.append(())
    summary.append((f"Файл: {source.name}", f"Проверено: {ru_date(today)}"))

    detail = wb.create_sheet("Строки")
    detail.append(ROWS_HEADER)
    for row, severity, title in issue_rows(issues):
        detail.append((row, str(severity), title, "открыть"))
        link = detail.cell(row=detail.max_row, column=4)
        link.hyperlink = f"{source.name}#'{sheet}'!A{row}"  # ссылка прямо на строку выгрузки
        link.font = Font(color="2B5DA8", underline="single")
        for cell in detail[detail.max_row][:3]:
            cell.fill = FILLS[severity]
    style_header(detail, (14, 16, 60, 10))

    wb.save(path)
