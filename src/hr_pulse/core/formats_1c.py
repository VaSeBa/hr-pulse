"""Форматы, в которых 1С выгружает даты и числа в Excel."""

from datetime import date


def ru_date(value: date | None) -> str:
    """Дата в формате 1С: date(2024, 1, 10) → "10.01.2024". Нет даты → пустая строка."""
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def format_count(number: int) -> str:
    """Число с неразрывным пробелом между тысячами, как в шапке отчёта 1С: 47075 → "47 075"."""
    return f"{number:,}".replace(",", "\xa0")
