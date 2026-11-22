"""Кто уходит: стаж на момент увольнения и ранняя текучесть.

Команда:  uv run python -m hr_pulse.analytics.tenure 01.2026 10.2026

Уволенных (входит в текучесть) раскладываем по «корзинам» стажа: до месяца,
1–3 месяца, 3–6, 6–12, 1–3 года, больше. Те, кто ушёл в первые 3 месяца, —
РАННЯЯ ТЕКУЧЕСТЬ: на их подбор, медосмотр, спецодежду, обучение и дорогу
потратились, а отдачи почти не получили. Их доля — главный показатель
качества подбора и адаптации.

Стаж — дни от приёма до увольнения включительно (как в шаге 6.2).
Печатает только числа и названия подразделений.
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path

# days_in_period понадобится в задаче 1; пока она не решена, ruff считает импорт лишним
# и при коммите удалил бы его сам. Пометка noqa просит не трогать. После решения — убрать.
from hr_pulse.analytics.departments import days_in_period  # noqa: F401
from hr_pulse.analytics.turnover import NO_DEPARTMENT, period_label
from hr_pulse.db.ssch import parse_month, ru_number
from hr_pulse.db.storage import DEFAULT_DB, connect
from hr_pulse.money.cost import cost_breakdown, rub, total
from hr_pulse.money.params import PARAMS_FILE, load_params

# (верхняя граница стажа в днях включительно, подпись). Кто дольше 1095 дней — LAST_BUCKET.
BUCKETS = [
    (30, "до 1 мес"),
    (91, "1–3 мес"),
    (182, "3–6 мес"),
    (365, "6–12 мес"),
    (1095, "1–3 года"),
]
LAST_BUCKET = "3 года и больше"
LABELS = [label for _limit, label in BUCKETS] + [LAST_BUCKET]
EARLY = ("до 1 мес", "1–3 мес")  # ранняя текучесть — первые 3 месяца

# Уволенные за период: подразделение и даты (без ФИО и табельных)
DISMISSED_SQL = """
SELECT COALESCE(top_department, :none) AS top_name, hire_date, fire_date
FROM episodes
WHERE counts_in_turnover = 1
  AND substr(fire_date, 1, 7) BETWEEN :start AND :end
"""


def tenure_days(hire: date, fire: date) -> int:
    """Стаж на момент увольнения в днях: принят и уволен в один день — 1. (Задача 1.)"""
    return days_in_period(hire, fire)


def bucket_for(days: int) -> str:
    """В какую корзину попадает стаж: 45 дней → «1–3 мес». (Пример к задаче 1.)"""
    for limit, label in BUCKETS:  # корзины по порядку, от коротких к длинным
        if days <= limit:  # первая, в которую помещается, — наша
            return label  # return сразу выходит из функции — дальше не смотрим
    return LAST_BUCKET  # ни одна не подошла — самая длинная


def count_buckets(days_list: list[int]) -> dict[str, int]:
    """Сколько уволенных в каждой корзине. Пустые корзины — тоже, с нулём. (Задача 1.)"""
    counts = {label: 0 for label in LABELS}
    for days in days_list:  # шаг 2: по каждому уволенному
        label = bucket_for(days)  #   его корзина
        counts[label] = counts[label] + 1
    return counts


def early_share(counts: dict[str, int]) -> float | None:
    """Доля ранней текучести, %: ушли в первые 3 месяца / все уволенные × 100. (Задача 2.)

    Никого не уволено — None: делить не на что.
    """
    all_dismissed = sum(counts.values())
    if all_dismissed == 0:  # ② шаг 2: делить не на что
        return None
    early = sum(counts[x] for x in EARLY)
    return early / all_dismissed * 100


def bar(share: float, scale: float = 2.5) -> str:
    """Полоска для текстовой диаграммы: 25 % → 10 квадратиков."""
    return "█" * round(share / scale)


def dismissed_rows(conn: sqlite3.Connection, start: str, end: str) -> list[tuple[str, int]]:
    """(подразделение, стаж в днях) для каждого уволенного за период."""
    params = {"start": start, "end": end, "none": NO_DEPARTMENT}
    return [
        (name, tenure_days(date.fromisoformat(hire), date.fromisoformat(fire)))
        for name, hire, fire in conn.execute(DISMISSED_SQL, params)
    ]


def by_department(rows: list[tuple[str, int]]) -> dict[str, list[int]]:
    """Стажи, разложенные по подразделениям: {"ОП Северное": [45, 400, …], …}."""
    result: dict[str, list[int]] = {}
    for name, days in rows:
        result.setdefault(name, []).append(days)
    return result


def describe_buckets(counts: dict[str, int]) -> list[str]:
    """Строки распределения: «  1–3 мес      40  18,3 %  ███████»."""
    all_dismissed = sum(counts.values())
    lines = []
    for label in LABELS:
        share = counts[label] / all_dismissed * 100 if all_dismissed else 0
        lines.append(f"{label:<16}{counts[label]:>5}{ru_number(share):>7} %  {bar(share)}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Стаж уволенных и ранняя текучесть")
    parser.add_argument("start", help="первый месяц, мм.гггг: 01.2026")
    parser.add_argument("end", nargs="?", help="последний месяц (по умолчанию = первый)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    parser.add_argument("--params", type=Path, default=PARAMS_FILE, help="файл параметров")
    args = parser.parse_args()

    try:
        start = parse_month(args.start)
        end = parse_month(args.end) if args.end else start
        params, _unknown = load_params(args.params)
        conn = connect(args.db)
        rows = dismissed_rows(conn, start, end)
    except ValueError as error:
        print(f"Не получилось: {error}")
        raise SystemExit(1) from error
    conn.close()

    label = period_label(start, end)
    if not rows:
        print(f"{label}: увольнений (входит в текучесть) нет")
        return

    counts = count_buckets([days for _name, days in rows])
    early = sum(counts[name] for name in EARLY)
    print(f"{label}: уволено (входит в текучесть) {len(rows)} — по стажу на момент увольнения:")
    for line in describe_buckets(counts):
        print(f"  {line}")
    share = early_share(counts)
    print(
        f"Ранняя текучесть (ушли в первые 3 месяца): {early} из {len(rows)} — {ru_number(share)} %"
    )
    per_person = total(cost_breakdown(params))
    cost = rub(early * per_person)
    print(f"Замена ушедших в первые 3 месяца — около {cost} (стоимость замены — шаг 7.1)")

    print("По подразделениям (ушли в первые 3 месяца / все уволенные, доля):")
    groups = by_department(rows)
    for name in sorted(groups, key=lambda n: -len(groups[n])):
        group = count_buckets(groups[name])
        group_early = sum(group[label] for label in EARLY)
        print(f"  {name} — {group_early} / {len(groups[name])}, {ru_number(early_share(group))} %")


if __name__ == "__main__":
    main()
