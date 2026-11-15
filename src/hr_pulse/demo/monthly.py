"""Демо «следующего месяца»: та же компания, но выгрузка на 31.10.2026.

Чтобы показать догрузку, нужен второй файл, где часть сотрудников уволилась
в октябре, а в октябре же пришли новые. Старые эпизоды берём из сентябрьской
демо-компании и меняем, новых создаём отдельно — с другим префиксом табельных.
"""

import random
from dataclasses import replace
from datetime import date

from hr_pulse.demo.generator import REASONS, FakeCompany, FakeRow, GeneratorConfig

OCTOBER_START = date(2026, 10, 1)
OCTOBER_END = date(2026, 10, 31)
FIRE_SHARE = 0.08  # доля работающих, уволенных в октябре
NEWCOMERS = 40  # сколько людей принято в октябре


def october_rows(rows: list[FakeRow], seed: int = 7) -> list[FakeRow]:
    """Сентябрьские строки → октябрьские: часть уволена в октябре, плюс новые сотрудники."""
    rng = random.Random(seed)
    reasons = [reason for reason, _ in REASONS]

    result = []
    for row in rows:
        episode = row.episode
        if episode.fire_date is None and rng.random() < FIRE_SHARE:
            fire = date(2026, 10, rng.randint(1, 31))
            episode = replace(episode, fire_date=fire, fire_reason=rng.choice(reasons))
        result.append(replace(row, episode=episode))

    config = GeneratorConfig(people=NEWCOMERS, start=OCTOBER_START, end=OCTOBER_END, seed=seed)
    for row in FakeCompany(config).generate():
        tab = row.episode.tab_number.replace("ДМ-", "ДН-")  # другой префикс — не пересечься
        result.append(replace(row, episode=replace(row.episode, tab_number=tab)))
    return result
