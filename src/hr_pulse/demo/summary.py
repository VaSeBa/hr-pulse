"""Быстрые сводки по сгенерированным данным — чтобы проверить, что генератор
правдоподобен."""

from datetime import date

from hr_pulse.demo.generator import FakeRow


def dismissals_by_year(rows: list[FakeRow]) -> dict[int, int]:
    """Сколько увольнений в каждом году: {2023: 1, 2024: 2}."""
    result: dict[int, int] = {}
    for row in rows:
        fire = row.episode.fire_date
        if fire is not None:
            result[fire.year] = result.get(fire.year, 0) + 1
    return result


def headcount_on(rows: list[FakeRow], day: date) -> int:
    """Сколько эпизодов числилось в списочном составе в этот день."""
    return sum(1 for row in rows if row.episode.is_employed_on(day))
