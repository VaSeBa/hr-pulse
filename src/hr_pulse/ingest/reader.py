"""Чтение выгрузок 1С из Excel: поиск строки заголовков и очистка служебных колонок.

Выгрузки 1С — это не «чистые» таблицы: над ними шапка отчёта, часть колонок
пустая, а заголовок бывает двухуровневым (группа сверху, названия колонок под ней).
Модуль находит, где начинается настоящая таблица, и отдаёт её как DataFrame.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hr_pulse.core.formats_1c import is_blank

HEADER_SEARCH_ROWS = 30  # заголовок ищем среди первых 30 строк
HEADER_MIN_SHARE = 0.6  # в строке заголовков заполнено ≥ 60% от самой «полной» строки
SUBHEADER_EMPTY_SHARE = 0.5  # под обычными заголовками строка подзаголовков пуста ≥ на 50%


@dataclass(frozen=True)
class LoadedTable:
    """Прочитанная таблица и сведения о том, как она найдена."""

    frame: pd.DataFrame  # сама таблица: колонки — заголовки, строки — данные
    header_row: int  # номер строки заголовков в Excel (с 1, как видит человек)
    header_depth: int = 1  # сколько строк занимает заголовок: 1 или 2


def read_raw(path: Path) -> pd.DataFrame:
    """Первый лист файла «как есть»: без заголовков, все значения — текстом."""
    return pd.read_excel(path, engine="calamine", header=None, dtype=str)


def find_header_row(raw: pd.DataFrame) -> int:
    """Номер строки заголовков (с 0) в «сыром» листе.

    Правило: среди первых строк найти самую заполненную, и взять первую строку,
    заполненную хотя бы на 60% от неё. Шапка отчёта над таблицей заполнена слабо
    (1–2 ячейки), строка заголовков — почти целиком.
    """
    filled = raw.head(HEADER_SEARCH_ROWS).notna().sum(axis=1)  # заполненных ячеек в строке

    if filled.empty or filled.max() == 0:
        raise ValueError("лист пустой: нет ни одной заполненной ячейки")

    threshold = filled.max() * HEADER_MIN_SHARE

    for row_number, count in filled.items():
        if count >= threshold:
            return int(row_number)

    raise ValueError("не удалось найти строку заголовков")


def has_subheader(raw: pd.DataFrame, header_index: int) -> bool:
    """Есть ли под строкой заголовков вторая строка — подзаголовки.

    Признаки строки подзаголовков (как в отчёте «Причины увольнений»):
    1) она заполняет «дырки» шапки — колонки под объединёнными ячейками;
    2) под обычными заголовками она в основном пустая.
    Строка данных первому признаку тоже может отвечать, но второму — нет.
    """
    if header_index + 1 >= len(raw):
        return False  # под заголовком ничего нет
    top = raw.iloc[header_index]
    below = raw.iloc[header_index + 1]

    fills_gaps = (top.isna() & below.notna()).any()  # хоть одна «дырка» шапки заполнена
    under_titles = below[top.notna()]  # ячейки под заполненными заголовками
    mostly_empty = under_titles.isna().mean() >= SUBHEADER_EMPTY_SHARE
    return bool(fills_gaps and mostly_empty)


def combine_headers(top: list, sub: list) -> list:
    """Склеить двухуровневый заголовок в один: где есть подзаголовок — берём его.

    ["Должность", "сотрудник", NaN]  +  [NaN, "Сотрудник.Таб. номер", "Сотрудник"]
    → ["Должность", "Сотрудник.Таб. номер", "Сотрудник"]
    """
    # Импорт is_blank наверху пока «серый» (не используется) — он нужен для этого задания.
    return [
        top_name if is_blank(sub_name) else sub_name
        for top_name, sub_name in zip(top, sub, strict=True)
    ]


def read_1c_table(path: Path) -> LoadedTable:
    """Прочитать выгрузку 1С с одно- или двухуровневым заголовком."""
    raw = read_raw(path)
    header_index = find_header_row(raw)

    header = list(raw.iloc[header_index])  # строка заголовков — обычным списком
    depth = 1
    if has_subheader(raw, header_index):
        header = combine_headers(header, list(raw.iloc[header_index + 1]))
        depth = 2

    frame = raw.iloc[header_index + depth :].copy()  # данные — ниже всех строк заголовка
    frame.columns = header

    frame = frame.dropna(axis="columns", how="all")  # убрать полностью пустые колонки
    frame = frame.dropna(axis="index", how="all")  # и полностью пустые строки
    frame = frame.reset_index(drop=True)  # пронумеровать строки заново с 0

    return LoadedTable(frame=frame, header_row=header_index + 1, header_depth=depth)


def describe(table: LoadedTable) -> str:
    """Краткое описание без персональных данных: где заголовок, сколько строк и колонок."""
    rows, columns = table.frame.shape
    if table.header_depth == 1:
        where = f"Заголовок в строке {table.header_row}"
    else:
        last = table.header_row + table.header_depth - 1
        where = f"Заголовок в строках {table.header_row}–{last}"
    return f"{where}, строк данных: {rows}, колонок: {columns}"
