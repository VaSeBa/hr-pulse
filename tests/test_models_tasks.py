"""Тесты для заданий шага 1.2: Episode.tenure_days и Person.is_rehired.

Сначала эти тесты падают — методов ещё нет. Напишите методы так,
чтобы все тесты стали зелёными. Сами тесты не меняйте.
"""

from datetime import date

import pytest

from hr_pulse.core.models import Episode, Person


def make_episode(hire_date: date, fire_date: date | None) -> Episode:
    return Episode(
        tab_number="00-0001",
        snils="112-233-445 95",
        position="Монтажник",
        department="Участок №1",
        hire_date=hire_date,
        fire_date=fire_date,
    )


# ---------- Задание 1: Episode.tenure_days ----------

FIRED = make_episode(date(2024, 1, 10), date(2024, 3, 31))
ACTIVE = make_episode(date(2024, 1, 10), None)


@pytest.mark.parametrize(
    ("episode", "on", "expected"),
    [
        pytest.param(FIRED, date(2024, 2, 15), 36, id="fired-on-middle-date"),
        pytest.param(FIRED, date(2025, 6, 1), 81, id="fired-counts-until-fire-date"),
        pytest.param(FIRED, date(2024, 1, 10), 0, id="hire-day-is-zero"),
        pytest.param(FIRED, date(2023, 12, 31), 0, id="before-hire-is-zero"),
        pytest.param(ACTIVE, date(2024, 12, 31), 356, id="active-counts-until-on"),
    ],
)
def test_tenure_days(episode, on, expected):
    assert episode.tenure_days(on) == expected


# ---------- Задание 2: Person.is_rehired ----------


def test_person_with_one_episode_is_not_rehired():
    person = Person(snils="112-233-445 95", episodes=(FIRED,))
    assert person.is_rehired is False


def test_person_with_two_episodes_is_rehired():
    second = make_episode(date(2025, 2, 1), None)
    person = Person(snils="112-233-445 95", episodes=(FIRED, second))
    assert person.is_rehired is True
