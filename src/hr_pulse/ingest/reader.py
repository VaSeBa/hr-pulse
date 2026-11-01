"""Чтение выгрузок 1С из Excel: поиск строки заголовков и очистка служебных колонок.

Выгрузки 1С — это не «чистые» таблицы: над ними шапка отчёта, часть колонок
пустая. Модуль находит, где начинается настоящая таблица, и отдаёт её как DataFrame.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HEADER_SEARCH_ROWS = 30  # заголовок ищем среди первых 30 строк
HEADER_MIN_SHARE = 0.6  # в строке заголовков заполнено ≥ 60% от самой «полной» строки


@dataclass(frozen=True)
class LoadedTable:
    """Прочитанная таблица и сведения о том, как она найдена."""

    frame: pd.DataFrame  # сама таблица: колонки — заголовки, строки — данные
    header_row: int  # номер строки заголовков в Excel (с 1, как видит человек)


def read_raw(path: Path) -> pd.DataFrame:
    """Первый лист файла «как есть»: без заголовков, все значения — текстом."""
    return pd.read_excel(path, engine="calamine", header=None, dtype=str)


def find_header_row(raw: pd.DataFrame) -> int:
    """Номер строки заголовков (с 0) в «сыром» листе.

    Правило: среди первых строк найти самую заполненную, и взять первую строку,
    заполненную хотя бы на 60% от неё. Шапка отчёта над таблицей заполнена слабо
    (1–2 ячейки), строка заголовков — почти целиком.
    """
    # Задание шага 2.1: напишите тело функции по плану из раздела 8 PDF.
    filled = raw.head(HEADER_SEARCH_ROWS).notna().sum(axis=1)  # заполненных ячеек в строке

    if filled.empty or filled.max() == 0:
        raise ValueError("лист пустой: нет ни одной заполненной ячейки")

    threshold = filled.max() * HEADER_MIN_SHARE

    for row_number, count in filled.items():
        if count >= threshold:
            return int(row_number)

    raise ValueError("не удалось найти строку заголовков")


def read_1c_table(path: Path) -> LoadedTable:
    """Прочитать выгрузку 1С с одноуровневым заголовком."""
    raw = read_raw(path)
    header_index = find_header_row(raw)

    frame = raw.iloc[header_index + 1 :].copy()  # всё, что ниже заголовка, — данные
    frame.columns = raw.iloc[header_index]  # строка заголовков — названия колонок

    frame = frame.dropna(axis="columns", how="all")  # убрать полностью пустые колонки
    frame = frame.dropna(axis="index", how="all")  # и полностью пустые строки
    frame = frame.reset_index(drop=True)  # пронумеровать строки заново с 0
    frame.columns.name = None  # убрать «имя» у набора колонок (осталось от строки)

    return LoadedTable(frame=frame, header_row=header_index + 1)


def describe(table: LoadedTable) -> str:
    """Краткое описание без персональных данных: где заголовок, сколько строк и колонок."""
    rows, columns = table.frame.shape
    return f"Заголовок в строке {table.header_row}, строк данных: {rows}, колонок: {columns}"
