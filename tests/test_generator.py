"""Тесты для hr_pulse.demo.generator."""

from collections import defaultdict
from datetime import timedelta

import pytest

from hr_pulse.core.snils import is_valid_snils
from hr_pulse.demo.generator import TECHNICAL_REASON, FakeCompany, GeneratorConfig

CONFIG = GeneratorConfig(people=500, seed=7)


@pytest.fixture(scope="module")
def rows():
    """Генерируем один раз на все тесты модуля — так быстрее."""
    return FakeCompany(CONFIG).generate()


def test_same_seed_gives_same_data(rows):
    again = FakeCompany(CONFIG).generate()
    assert [r.episode for r in rows] == [r.episode for r in again]


def test_different_seed_gives_different_data(rows):
    other = FakeCompany(GeneratorConfig(people=500, seed=8)).generate()
    assert [r.episode for r in rows] != [r.episode for r in other]


def test_every_snils_is_valid(rows):
    assert all(is_valid_snils(r.episode.snils) for r in rows)


def test_tab_numbers_are_unique(rows):
    tabs = [r.episode.tab_number for r in rows]
    assert len(tabs) == len(set(tabs))


def test_dates_inside_period(rows):
    for r in rows:
        assert CONFIG.start <= r.episode.hire_date <= CONFIG.end
        assert r.episode.fire_date is None or r.episode.fire_date <= CONFIG.end


def test_reasons_only_since_2024(rows):
    for r in rows:
        fire = r.episode.fire_date
        if fire is None or fire < CONFIG.reasons_from:
            assert r.episode.fire_reason is None
        else:
            assert r.episode.fire_reason is not None


def test_some_people_are_rehired(rows):
    episodes_by_snils = defaultdict(list)
    for r in rows:
        episodes_by_snils[r.episode.snils].append(r.episode)
    assert len(episodes_by_snils) == CONFIG.people
    assert any(len(episodes) > 1 for episodes in episodes_by_snils.values())


def test_technical_rehire_is_next_day(rows):
    hires = {(r.episode.snils, r.episode.hire_date) for r in rows}
    technical = [r.episode for r in rows if r.episode.fire_reason == TECHNICAL_REASON]
    assert technical  # такие увольнения есть
    for e in technical:
        assert (e.snils, e.fire_date + timedelta(days=1)) in hires


def test_early_leave_share_is_realistic(rows):
    # Берём только тех, кто принят больше чем за 90 дней до выгрузки
    old_enough = [r.episode for r in rows if r.episode.hire_date < CONFIG.end - timedelta(days=90)]
    early = [e for e in old_enough if e.fire_date and (e.fire_date - e.hire_date).days <= 90]
    share = len(early) / len(old_enough)
    assert 0.18 < share < 0.32  # задано 25%; случайность даёт небольшой разброс


def test_full_name_has_three_parts(rows):
    assert all(len(r.full_name.split()) == 3 for r in rows)


def test_active_have_no_reason(rows):
    for r in rows:
        if r.episode.fire_date is None:
            assert r.episode.fire_reason is None
