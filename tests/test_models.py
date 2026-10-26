"""Тесты для hr_pulse.core.models."""

from datetime import date

import pytest

from hr_pulse.core.models import Episode, Person

# Выдуманный сотрудник: принят 10.01.2024, уволен 31.03.2024
HIRE = date(2024, 1, 10)
FIRE = date(2024, 3, 31)


def make_episode(fire_date: date | None = FIRE, hire_date: date = HIRE) -> Episode:
    """Вспомогательная функция: эпизод с выдуманными данными, меняем только даты."""
    return Episode(
        tab_number="00-0001",
        snils="112-233-445 95",
        position="Монтажник",
        department="Участок №1",
        hire_date=hire_date,
        fire_date=fire_date,
    )


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2024, 1, 9), False, id="day-before-hire"),
        pytest.param(date(2024, 1, 10), True, id="hire-day"),
        pytest.param(date(2024, 2, 15), True, id="middle"),
        pytest.param(date(2024, 3, 31), True, id="fire-day-included"),
        pytest.param(date(2024, 4, 1), False, id="day-after-fire"),
    ],
)
def test_is_employed_on(day, expected):
    assert make_episode().is_employed_on(day) is expected


def test_active_employee_employed_any_day_after_hire():
    episode = make_episode(fire_date=None)
    assert episode.is_active is True
    assert episode.is_employed_on(date(2030, 1, 1)) is True


def test_fired_employee_is_not_active():
    assert make_episode().is_active is False


def test_fire_before_hire_is_rejected():
    with pytest.raises(ValueError):
        make_episode(fire_date=date(2024, 1, 1))


def test_fire_on_hire_day_is_allowed():
    # Принят и уволен в один день — редко, но законно
    assert make_episode(fire_date=HIRE).is_employed_on(HIRE) is True


def test_episode_is_frozen():
    episode = make_episode()
    with pytest.raises(AttributeError):
        episode.position = "Сварщик"


def test_person_first_hire_date():
    first = make_episode(hire_date=date(2021, 5, 1), fire_date=date(2021, 12, 31))
    second = make_episode(hire_date=date(2023, 2, 1), fire_date=None)
    person = Person(snils="112-233-445 95", episodes=(second, first))
    assert person.first_hire_date == date(2021, 5, 1)


def test_snils_hidden_in_repr():
    # Защита ПДн: при печати объекта (в лог, в консоль) СНИЛС не виден
    episode = make_episode()
    assert "112-233-445" not in repr(episode)
    person = Person(snils="112-233-445 95", episodes=(episode,))
    assert "112-233-445" not in repr(person)
