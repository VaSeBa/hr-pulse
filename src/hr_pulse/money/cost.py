"""Стоимость текучести за период: сколько стоит заменить ушедших.

Команда:  uv run python -m hr_pulse.money.cost 07.2026 09.2026

Стоимость замены одного сотрудника = прямые затраты (подбор, медосмотр,
обучение, спецодежда, проезд, оформление) + недополученная выработка, пока
новичок не вышел на полную производительность:

    зарплата × месяцев адаптации × доля потерянной выработки

Стоимость текучести = уволенные (входит в текучесть) × стоимость замены.
Параметры — в hr_pulse.money.params; их меняет пользователь.
"""

import argparse
from pathlib import Path

from hr_pulse.analytics.turnover import dismissed_by_department, period_label, period_turnover
from hr_pulse.db.ssch import parse_month
from hr_pulse.db.storage import DEFAULT_DB, connect
from hr_pulse.money.params import PARAMS_FILE, load_params

# Прямые затраты: ключ параметра → строка расшифровки
DIRECT_ITEMS = {
    "подбор": "Подбор",
    "медосмотр": "Медосмотр",
    "обучение": "Обучение и аттестация",
    "спецодежда": "Спецодежда и СИЗ",
    "проезд": "Проезд на первую вахту",
    "оформление": "Оформление",
}
RAMP_UP = "Недополученная выработка в адаптацию"


def rub(value: float) -> str:
    """15000 → «15 000 ₽»: целые рубли, пробел между тысячами."""
    return f"{round(value):,} ₽".replace(",", " ")


def total(rows: list[tuple[str, float]]) -> float:
    """Сумма вторых элементов пар. (Пример к задаче 2.)"""
    result = 0.0  # копилка
    for _label, amount in rows:  # по каждой паре «название, сумма»
        result += amount
    return result


def cost_breakdown(params: dict[str, float]) -> list[tuple[str, float]]:
    """Стоимость замены одного сотрудника по статьям: [(«Подбор», 15000.0), …]."""
    rows = []
    for key in DIRECT_ITEMS:
        rows.append((DIRECT_ITEMS[key], params[key]))  # сумма — значение параметра с этим ключом
    ramp_up = params["зарплата"] * params["адаптация_мес"] * params["потеря_выработки"] / 100
    rows.append((RAMP_UP, ramp_up))
    return rows


def cost_by_department(
    dismissed: list[tuple[str, int]], per_person: float
) -> list[tuple[str, int, float]]:
    """(ОП, уволено, стоимость) — в том же порядке, что пришли (больше уволенных — выше)."""
    return [(name, count, count * per_person) for name, count in dismissed]


def main() -> None:
    parser = argparse.ArgumentParser(description="Стоимость текучести за период")
    parser.add_argument("start", help="первый месяц, мм.гггг: 07.2026")
    parser.add_argument("end", nargs="?", help="последний месяц (по умолчанию = первый)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    parser.add_argument("--params", type=Path, default=PARAMS_FILE, help="файл параметров")
    args = parser.parse_args()

    try:
        start = parse_month(args.start)
        end = parse_month(args.end) if args.end else start
        params, unknown = load_params(args.params)
        conn = connect(args.db)
        turnover = period_turnover(conn, start, end)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error
    for key in unknown:
        print(f"В файле параметров незнакомый параметр «{key}» — пропущен")

    breakdown = cost_breakdown(params)
    per_person = total(breakdown)
    print(f"{period_label(start, end)}: уволено (входит в текучесть) {turnover.dismissed}")
    print(f"Стоимость замены одного сотрудника — {rub(per_person)}:")
    for label, amount in breakdown:
        print(f"  {label} — {rub(amount)}")
    print(f"Стоимость текучести за период — {rub(turnover.dismissed * per_person)}")
    rows = cost_by_department(dismissed_by_department(conn, start, end), per_person)
    if rows:
        print("По подразделениям:")
        for name, count, cost in rows:
            print(f"  {name} — {count} × {rub(per_person)} = {rub(cost)}")
    if not args.params.exists():
        print("Параметры — примерные значения по умолчанию. Задайте свои: hr_pulse.money.params")
    conn.close()


if __name__ == "__main__":
    main()
