"""Модели предметной области: эпизод занятости и человек."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Episode:
    """Эпизод занятости — один период работы человека от приёма до увольнения.

    Один человек (один СНИЛС) может иметь несколько эпизодов: уволился и был принят снова.
    """

    tab_number: str
    snils: str = field(repr=False)  # ПДн: не показываем при печати объекта
    position: str
    department: str
    hire_date: date
    fire_date: date | None = None  # None — работает до сих пор
    fire_reason: str | None = None

    def __post_init__(self) -> None:
        """Проверка сразу после создания: эпизод с невозможными датами не создаётся."""
        if self.fire_date is not None and self.fire_date < self.hire_date:
            raise ValueError("дата увольнения раньше даты приёма")

    @property
    def is_active(self) -> bool:
        """Работает ли сотрудник сейчас (нет даты увольнения)."""
        return self.fire_date is None

    def is_employed_on(self, day: date) -> bool:
        """Числился ли сотрудник в списочном составе в этот день.

        День увольнения включается: по ст. 84.1 ТК РФ это последний день работы.
        """
        if day < self.hire_date:
            return False
        return self.fire_date is None or day <= self.fire_date


@dataclass(frozen=True)
class Person:
    """Человек — все эпизоды занятости с одним СНИЛС."""

    snils: str = field(repr=False)  # ПДн: не показываем при печати объекта
    episodes: tuple[Episode, ...]

    @property
    def first_hire_date(self) -> date:
        """Дата самого первого приёма."""
        return min(episode.hire_date for episode in self.episodes)
