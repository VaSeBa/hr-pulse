"""«Испорченная» демо-выгрузка: в неё нарочно внесены типичные ошибки.

На ней видно, как работает проверка качества данных. Ошибки вносятся прямо
в ячейки готового Excel-файла — так же, как они появляются в жизни: руками.
"""

from datetime import timedelta
from pathlib import Path

from openpyxl import load_workbook

from hr_pulse.core.formats_1c import parse_ru_date, ru_date
from hr_pulse.core.snils import snils_checksum

# Колонки выгрузки «Личные данные сотрудников» (см. EMPLOYEES_HEADER в export_1c.py)
TAB, POSITION, HIRE, FIRE, SNILS = "A", "F", "G", "H", "J"


def spoil_employees(path: Path) -> dict[str, list[int]]:
    """Внести ошибки в файл сотрудников. Возвращает «что испорчено → строки Excel»."""
    wb = load_workbook(path)
    ws = wb.active

    ws[f"{SNILS}12"] = None  # пустой СНИЛС

    snils = ws[f"{SNILS}15"].value  # неверное контрольное число: меняем последние 2 цифры
    control = (int(snils[-2:]) + 1) % 100
    ws[f"{SNILS}15"] = f"{snils[:-2]}{control:02d}"

    ws[f"{HIRE}18"] = "31.02.2024"  # такой даты не бывает

    hire = parse_ru_date(ws[f"{HIRE}21"].value)  # уволен раньше, чем принят
    ws[f"{FIRE}21"] = ru_date(hire - timedelta(days=30))

    ws[f"{HIRE}24"] = "01.01.2031"  # дата из будущего (а увольнение убираем,
    ws[f"{FIRE}24"] = None  # чтобы не получилось ещё и «уволен раньше приёма»)

    ws[f"{TAB}27"] = ws[f"{TAB}26"].value  # повтор табельного номера

    ws[f"{POSITION}30"] = None  # пустая должность

    # СНИЛС с ведущим нулём, записанный как ЧИСЛО: Excel ноль «съест»
    number = "012345678"
    ws[f"{SNILS}36"] = int(f"{number}{snils_checksum(number):02d}")

    # Повторно принятый человек: во втором эпизоде СНИЛС записан без дефисов и пробела
    first, second = _first_rehire_after(ws, row=40)
    ws[f"{SNILS}{second}"] = ws[f"{SNILS}{first}"].value.replace("-", "").replace(" ", "")

    wb.save(path)
    return {
        "snils_blank": [12],
        "snils_invalid": [15],
        "not_a_date": [18],
        "fire_before_hire": [21],
        "future": [24],
        "duplicate_tab": [26, 27],
        "position_blank": [30],
        "snils_lost_zeros": [36],
        "snils_forms": [first, second],
    }


def _first_rehire_after(ws, row: int) -> tuple[int, int]:
    """Две строки (ниже row) с одним СНИЛС — эпизоды одного повторно принятого человека."""
    seen: dict[str, int] = {}
    for current in range(row, ws.max_row + 1):
        value = ws[f"{SNILS}{current}"].value
        if value in seen:
            return seen[value], current
        seen[value] = current
    raise ValueError("в демо-выгрузке нет повторно принятых")
