"""Превращение текстовых колонок выгрузки в настоящие типы: даты.

Читаем мы всё текстом (dtype=str) — так ничего не теряется. А здесь осознанно
превращаем нужные колонки в даты, чтобы потом считать стаж и текучесть.
"""

import pandas as pd

from hr_pulse.core.formats_1c import parse_ru_date


def parse_date_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Копия таблицы, в которой указанные колонки — даты (date) или None для пустых."""
    result = frame.copy()  # исходную таблицу не трогаем
    for name in columns:
        result[name] = result[name].map(parse_ru_date)  # применить к каждой ячейке
    return result


def date_share(column: pd.Series) -> float:
    """Какая доля заполненных ячеек колонки похожа на дату: 0.0 … 1.0.

    Нужна, чтобы узнать колонку с датами, даже если она неверно подписана
    (как «Адрес места проживания» в настоящей выгрузке).
    """
    values = column.dropna()  # пустые не считаем
    if values.empty:
        return 0.0
    good = 0
    for value in values:
        try:
            parse_ru_date(value)
        except ValueError:
            continue
        good += 1
    return good / len(values)
