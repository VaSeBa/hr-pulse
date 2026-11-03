"""Форматы, в которых 1С выгружает даты и числа в Excel — туда и обратно.

«Туда» (ru_date, format_count) нужно демо-экспорту: записать как 1С.
«Обратно» (parse_ru_date, parse_count) нужно чтению: превратить текст из выгрузки
в настоящие даты и числа, с которыми можно считать.
"""

import math
from datetime import date, datetime

# Как может выглядеть дата в ячейке, если читать её текстом:
# «10.01.2024» — дата, записанная 1С как текст (наш основной случай);
# «2024-01-10 00:00:00» — настоящая дата Excel, прочитанная как текст (dtype=str);
# «2024-01-10» — то же без времени.
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def ru_date(value: date | None) -> str:
    """Дата в формате 1С: date(2024, 1, 10) → "10.01.2024". Нет даты → пустая строка."""
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def format_count(number: int) -> str:
    """Число с неразрывным пробелом между тысячами, как в шапке отчёта 1С: 47075 → "47 075"."""
    return f"{number:,}".replace(",", "\xa0")


def is_blank(value: object) -> bool:
    """Пустая ли ячейка: None, NaN (так pandas пишет пустоту) или строка из одних пробелов."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def parse_ru_date(value: object) -> date | None:
    """Текст из выгрузки → дата: "10.01.2024" → date(2024, 1, 10). Пустая ячейка → None.

    Не дата → ValueError: лучше честно остановиться, чем молча потерять увольнение.
    """
    if is_blank(value):
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue  # не этот формат — пробуем следующий
    raise ValueError(f"не похоже на дату: {text!r}")


def parse_count(value: object) -> int:
    """Число из шапки отчёта: "47 075" (с неразрывным пробелом) → 47075.

    Пустое значение или не число → ValueError.
    """
    if is_blank(value):
        raise ValueError("пустое значение вместо числа")

    text = str(value).replace("\xa0", "").replace(" ", "")
    if not text.isdigit():
        raise ValueError(f"не похоже на число: {value!r}")
    return int(text)
