"""Параметры стоимости текучести — их меняет пользователь.

Команды:  uv run python -m hr_pulse.money.params                 — показать
          uv run python -m hr_pulse.money.params проезд 30000    — изменить один
          uv run python -m hr_pulse.money.params --reset         — вернуть по умолчанию

Параметры хранятся в data/cost_params.json — обычный текстовый файл JSON,
его можно открыть и в блокноте. Папка data/ в .gitignore: ваши суммы
в репозиторий не попадут.

ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ — ПРИМЕРНЫЕ, для демонстрации. Замените их своими
(спросите у рекрутинга, ОТ, бухгалтерии, сколько это стоит у вас).
"""

import argparse
import json
from pathlib import Path

from hr_pulse.core.formats_1c import is_blank

PARAMS_FILE = Path("data") / "cost_params.json"

# Ключ → значение по умолчанию. Ключи по-русски: их набирают в командной строке.
DEFAULTS: dict[str, float] = {
    "подбор": 15_000,  # ₽: вакансия, работа рекрутёра
    "медосмотр": 5_000,  # ₽: при приёме
    "обучение": 12_000,  # ₽: ОТ, промбезопасность, аттестация
    "спецодежда": 18_000,  # ₽: СИЗ на первую вахту
    "проезд": 25_000,  # ₽: первый заезд на вахту
    "оформление": 3_000,  # ₽: приём и увольнение (кадры, бухгалтерия)
    "зарплата": 120_000,  # ₽ в месяц: средняя, с взносами
    "адаптация_мес": 1.5,  # месяцев до полной выработки
    "потеря_выработки": 50,  # % выработки, недополученной в адаптацию
}

LABELS = {
    "подбор": "Подбор (вакансия, работа рекрутёра), ₽",
    "медосмотр": "Медосмотр при приёме, ₽",
    "обучение": "Обучение и аттестация (ОТ, ПБ), ₽",
    "спецодежда": "Спецодежда и СИЗ, ₽",
    "проезд": "Проезд на первую вахту, ₽",
    "оформление": "Оформление приёма и увольнения, ₽",
    "зарплата": "Средняя зарплата с взносами, ₽ в месяц",
    "адаптация_мес": "Адаптация до полной выработки, месяцев",
    "потеря_выработки": "Недополученная выработка в адаптацию, %",
}


def parse_amount(text: str) -> float:
    """«30 000», «30000 ₽», «1,5», «50 %» → число. Пусто, не число или меньше нуля — ValueError."""
    if is_blank(text):
        raise ValueError("значение не указано")
    cleaned = str(text)
    for junk in ("\xa0", " ", "₽", "руб.", "руб", "%"):
        cleaned = cleaned.replace(junk, "")
    try:
        value = float(cleaned.replace(",", "."))
    except ValueError as error:
        raise ValueError(f"это не число: {text!r}") from error
    if value < 0:
        raise ValueError("значение не может быть меньше нуля")
    return value


def changed_keys(params: dict[str, float]) -> list[str]:
    """Какие параметры отличаются от значений по умолчанию. (Пример к задаче 1.)"""
    changed = []  # копилка-список
    for key, value in params.items():  # по каждой паре «ключ, значение»
        if key in DEFAULTS and value != DEFAULTS[key]:  # ключ знакомый, а значение другое
            changed.append(key)
    return changed


def merge_params(saved: dict) -> tuple[dict[str, float], list[str]]:
    """Значения по умолчанию, поверх них — сохранённые. (Задача 1.)

    Незнакомые ключи (опечатка в файле, старое название) не берём —
    возвращаем их списком, чтобы показать человеку.
    """
    params = dict(DEFAULTS)
    unknown = []
    for key, value in saved.items():
        if key not in DEFAULTS:
            unknown.append(key)
            continue
        params[key] = float(value)  # шаг 4: знакомый — заменить значение
    return params, unknown


def load_params(path: Path = PARAMS_FILE) -> tuple[dict[str, float], list[str]]:
    """Параметры из файла; файла нет — значения по умолчанию. Испорченный файл — ValueError."""
    if not path.exists():
        return dict(DEFAULTS), []
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"файл {path.name} испорчен: {error.msg}, строка {error.lineno}"
        ) from error
    if not isinstance(saved, dict):
        raise ValueError(f'в файле {path.name} должен быть словарь {{"ключ": число}}')
    return merge_params(saved)


def save_params(params: dict[str, float], path: Path = PARAMS_FILE) -> None:
    """Записать параметры в JSON: по-русски, с отступами — чтобы читалось глазами."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tidy = {key: int(value) if value == int(value) else value for key, value in params.items()}
    path.write_text(json.dumps(tidy, ensure_ascii=False, indent=2), encoding="utf-8")


def format_value(value: float) -> str:
    """«15 000», «1,5», «50» — как показывать параметр."""
    if value == int(value):
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.1f}".replace(",", " ").replace(".", ",")


def describe_params(params: dict[str, float]) -> list[str]:
    """Строки «проезд — 25 000 (Проезд на первую вахту, ₽)»."""
    return [f"{key} — {format_value(params[key])} ({LABELS[key]})" for key in DEFAULTS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Параметры стоимости текучести")
    parser.add_argument("key", nargs="?", help="какой параметр изменить: " + ", ".join(DEFAULTS))
    parser.add_argument("value", nargs="?", help="новое значение")
    parser.add_argument("--reset", action="store_true", help="вернуть значения по умолчанию")
    parser.add_argument("--file", type=Path, default=PARAMS_FILE, help="файл (%(default)s)")
    args = parser.parse_args()

    try:
        params, unknown = load_params(args.file)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error
    for key in unknown:
        print(f"В файле незнакомый параметр «{key}» — пропущен")

    if args.reset:
        save_params(dict(DEFAULTS), args.file)
        print("Параметры возвращены к значениям по умолчанию")
        params = dict(DEFAULTS)
    elif args.key:
        if args.key not in DEFAULTS:
            parser.error(f"нет параметра «{args.key}»; есть: {', '.join(DEFAULTS)}")
        if args.value is None:
            parser.error("укажите новое значение")
        try:
            new = parse_amount(args.value)
        except ValueError as error:
            parser.error(str(error))
        if args.key == "потеря_выработки" and new > 100:
            parser.error("потеря выработки — в процентах, от 0 до 100")
        old = params[args.key]
        params[args.key] = new
        save_params(params, args.file)
        print(f"{args.key}: было {format_value(old)}, стало {format_value(new)}")

    source = args.file if args.file.exists() else "значения по умолчанию (примерные!)"
    print(f"Параметры стоимости — {source}:")
    for line in describe_params(params):
        print(f"  {line}")
    changed = changed_keys(params)
    if changed:
        print(f"Изменены вами: {', '.join(changed)}")
    else:
        print("Все значения — по умолчанию (примерные). Замените их своими.")


if __name__ == "__main__":
    main()
