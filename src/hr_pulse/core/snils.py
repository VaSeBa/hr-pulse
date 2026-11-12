"""СНИЛС: приведение к цифрам, проверка контрольного числа, форматирование и маскирование.

Важно: функции модуля никогда не включают сам номер СНИЛС в тексты ошибок,
чтобы персональные данные не попали в журналы и сообщения программы.
"""

import re

from hr_pulse.core.formats_1c import is_blank

SNILS_LENGTH = 11  # 9 цифр номера + 2 цифры контрольного числа
NO_CHECK_LIMIT = 1_001_998  # номера до 001-001-998 выдавались без проверки контрольного числа


class SnilsError(ValueError):
    """СНИЛС невозможно привести к правильному виду."""


def snils_digits(raw: str) -> str:
    """Оставляет в СНИЛС только цифры и проверяет, что их ровно 11.

    "112-233-445 95" → "11223344595". Если цифр не 11 — ошибка SnilsError.
    """
    digits = re.sub(r"\D", "", raw)  # \D — любой символ, кроме цифры
    if len(digits) != SNILS_LENGTH:
        # В сообщении — только количество цифр, сам номер не показываем (ПДн)
        raise SnilsError(f"в СНИЛС должно быть {SNILS_LENGTH} цифр, найдено {len(digits)}")
    return digits


def snils_checksum(number: str) -> int:
    """Считает контрольное число для 9 цифр номера СНИЛС.

    Каждая цифра умножается на вес: первая на 9, вторая на 8, …, девятая на 1.
    Сумма делится на 101, остаток — контрольное число; остаток 100 записывается как 0.
    """
    total = sum(int(digit) * (9 - position) for position, digit in enumerate(number))
    check = total % 101
    return 0 if check == 100 else check


def is_valid_snils(raw: str) -> bool:
    """True, если СНИЛС правильный: 11 цифр и верное контрольное число."""
    try:
        digits = snils_digits(raw)
    except SnilsError:
        return False

    number, control = digits[:9], int(digits[9:])  # срезы: первые 9 цифр и последние 2

    if number == "000000000":  # пустой номер из одних нулей
        return False
    if int(number) <= NO_CHECK_LIMIT:  # старые номера: контрольное число не проверяется
        return True
    return snils_checksum(number) == control


def format_snils(raw: str) -> str:
    """Приводит СНИЛС к виду "XXX-XXX-XXX YY"."""
    digits = snils_digits(raw)  # если цифр не 11 — SnilsError поднимется отсюда
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:]}"


def mask_snils(raw: str) -> str:
    """Скрывает номер СНИЛС, оставляя только контрольное число: "***-***-*** 95"."""
    try:
        digits = snils_digits(raw)
    except SnilsError:
        return "***-***-*** **"  # испорченный СНИЛС скрываем целиком, но не падаем
    return f"***-***-*** {digits[9:]}"


def restore_zeros(text: str) -> str:
    """Вернуть ведущие нули СНИЛС, который Excel хранил как число.

    В ячейке-числе 01234567890 превращается в 1234567890 — ноль пропадает.
    Если в тексте только цифры и их меньше 11 — дописываем нули слева.
    Всё остальное возвращаем как есть.
    """
    if text.isdigit() and len(text) < SNILS_LENGTH:
        return text.zfill(SNILS_LENGTH)
    return text


def clean_snils(value: object) -> str | None:
    """СНИЛС к единому виду «XXX-XXX-XXX YY»: так один человек — одно значение.

    "11223344595", " 112-233-445 95 ", число без ведущего нуля → один и тот же вид.
    Пусто или цифр не 11 → None (такие строки найдёт проверка качества).
    """
    if is_blank(value):
        return None
    text = restore_zeros(str(value).strip())
    try:
        return format_snils(text)
    except SnilsError:
        return None
