"""Генератор выдуманных сотрудников: приёмы, увольнения, повторные приёмы, причины.

Все данные вымышлены: ФИО составлены Faker из случайных имён и фамилий,
СНИЛС — случайные номера с правильным контрольным числом.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

from hr_pulse.core.models import Episode
from hr_pulse.core.snils import NO_CHECK_LIMIT, format_snils, snils_checksum

# ---------- Справочники выдуманной компании ----------


@dataclass(frozen=True)
class Unit:
    """Подразделение со всей «вертикалью» над ним."""

    department: str
    top_department: str
    functional_block: str
    functional_subordination: str


# Подразделения по типу работы: "field" — стройка, "transport" — техника, "office" — офис
UNITS = {
    "field": (
        Unit("СМУ-1 Участок №1", "ОП Северное", "ЗГД по производству", "Производство"),
        Unit("СМУ-1 Участок №2", "ОП Северное", "ЗГД по производству", "Производство"),
        Unit("СМУ-2 Участок №1", "ОП Заполярное", "ЗГД по производству", "Производство"),
        Unit("Участок изоляции", "ОП Восточное", "ЗГД по производству", "Производство"),
    ),
    "transport": (
        Unit("Автоколонна №1", "ОП Заполярное", "Главный инженер", "Департамент механика"),
        Unit("Автоколонна №2", "ОП Северное", "Главный инженер", "Департамент механика"),
    ),
    "office": (
        Unit("Отдел кадров", "ОП Центральное", "ЗГД по персоналу", "Департамент персонала"),
        Unit("Производственно-технический отдел", "ОП Центральное", "Главный инженер", "ПТО"),
    ),
}

# (должность, категория персонала, где работает, вес — как часто встречается)
POSITIONS = (
    ("Монтажник технологических трубопроводов 5 разряда", "Основные", "field", 18),
    ("Электросварщик ручной сварки 6 разряда", "Основные", "field", 14),
    ("Монтажник стальных конструкций 4 разряда", "Основные", "field", 14),
    ("Изолировщик на термоизоляции 4 разряда", "Основные", "field", 8),
    ("Машинист экскаватора 6 разряда", "Машинисты", "transport", 8),
    ("Водитель автомобиля", "Водители", "transport", 8),
    ("Мастер участка", "Линейные руководители", "field", 5),
    ("Начальник участка", "Руководители", "field", 1),
    ("Инженер ПТО", "Специалисты", "office", 4),
    ("Специалист по кадрам", "Специалисты", "office", 2),
)

# (причина увольнения по мнению HR, вес)
REASONS = (
    ("Оплата труда: низкая зп", 30),
    ("Работа в регионе проживания", 17),
    ("Несоблюдение ПВТР", 15),
    ("Необходимость решения личных вопросов по месту жительства", 8),
    ("Проблемы со своим здоровьем", 7),
    ("Неудовлетворенность работой вахтовым методом", 6),
    ("Пропал/не выходит на связь", 5),
    ("Истечение срока патента, согласования ФСБ, др. спец.права", 5),
    ("Окончание срока действия трудового договора", 5),
    ("Выход на пенсию", 2),
)
TECHNICAL_REASON = "Завершение объекта строительства"


# ---------- Настройки и результат ----------


@dataclass(frozen=True)
class GeneratorConfig:
    """Параметры выдуманной компании. Меняя их, получаем разные сценарии."""

    people: int = 2000  # сколько разных людей (СНИЛС)
    start: date = date(2021, 1, 1)  # первый возможный приём
    end: date = date(2026, 9, 30)  # дата выгрузки: позже неё событий нет
    seed: int = 42  # «зерно» случайности: одно зерно — одни и те же данные
    male_share: float = 0.92  # доля мужчин (вахтовое строительство)
    early_leave_share: float = 0.25  # доля уходящих в первые 90 дней
    median_tenure_days: int = 420  # медиана стажа у остальных
    rehire_share: float = 0.15  # доля уволенных, которых принимают снова
    technical_share: float = 0.5  # из них — переоформление на следующий день
    reasons_from: date = date(2024, 1, 1)  # причины увольнения ведутся с этой даты


@dataclass(frozen=True)
class FakeRow:
    """Одна строка будущей выгрузки: эпизод + то, чего нет в модели эпизода."""

    episode: Episode
    full_name: str = field(repr=False)  # ПДн, хоть и выдуманные: не печатаем
    unit: Unit
    staff_category: str


# ---------- Генератор ----------


class FakeCompany:
    """Выдуманная компания. Вызовите generate(), чтобы получить строки выгрузки."""

    def __init__(self, config: GeneratorConfig | None = None) -> None:
        self.config = config or GeneratorConfig()
        self.rng = random.Random(self.config.seed)  # свой генератор случайных чисел
        self.faker = Faker("ru_RU")
        self.faker.seed_instance(self.config.seed)
        self._tab_counter = 0
        self._used_snils: set[str] = set()

    def generate(self) -> list[FakeRow]:
        """Все эпизоды всех людей, отсортированные по дате приёма."""
        rows: list[FakeRow] = []
        for _ in range(self.config.people):
            rows.extend(self._person_rows())
        rows.sort(key=lambda row: row.episode.hire_date)
        return rows

    def _person_rows(self) -> list[FakeRow]:
        """Один человек: первый приём и, возможно, повторные."""
        cfg = self.config
        snils = self._new_snils()
        full_name = self._new_name()
        position, category, place = self._pick_position()
        unit = self.rng.choice(UNITS[place])  # подразделение подходящего типа
        hire = cfg.start + timedelta(days=self.rng.randint(0, (cfg.end - cfg.start).days))

        rows: list[FakeRow] = []
        while True:  # каждый проход цикла — один эпизод занятости
            fire = self._fire_date(hire)
            reason = None
            next_hire = None

            if fire is not None:
                reason = self._pick_reason()
                if self.rng.random() < cfg.rehire_share:  # этого человека примут снова
                    if self.rng.random() < cfg.technical_share:
                        reason = TECHNICAL_REASON  # объект завершён — переоформление
                        next_hire = fire + timedelta(days=1)
                    else:
                        next_hire = fire + timedelta(days=self.rng.randint(30, 400))
                if fire < cfg.reasons_from:
                    reason = None  # до 2024 года причины не вели

            episode = Episode(
                tab_number=self._new_tab_number(),
                snils=snils,
                position=position,
                department=unit.department,
                hire_date=hire,
                fire_date=fire,
                fire_reason=reason,
            )
            rows.append(FakeRow(episode, full_name, unit, category))

            if next_hire is None or next_hire > cfg.end:
                return rows
            hire = next_hire  # следующий эпизод того же человека

    def _fire_date(self, hire: date) -> date | None:
        """Дата увольнения или None, если человек работает на дату выгрузки."""
        cfg = self.config
        if self.rng.random() < cfg.early_leave_share:
            tenure = self.rng.randint(1, 90)  # ушёл в первые три месяца
        else:
            rate = math.log(2) / cfg.median_tenure_days
            tenure = 90 + int(self.rng.expovariate(rate))
        fire = hire + timedelta(days=tenure)
        return None if fire > cfg.end else fire

    def _pick_position(self) -> tuple[str, str, str]:
        weights = [weight for *_, weight in POSITIONS]
        position, category, place, _ = self.rng.choices(POSITIONS, weights=weights)[0]
        return position, category, place

    def _pick_reason(self) -> str:
        weights = [weight for _, weight in REASONS]
        return self.rng.choices(REASONS, weights=weights)[0][0]

    def _new_name(self) -> str:
        if self.rng.random() < self.config.male_share:
            parts = (
                self.faker.last_name_male(),
                self.faker.first_name_male(),
                self.faker.middle_name_male(),
            )
        else:
            parts = (
                self.faker.last_name_female(),
                self.faker.first_name_female(),
                self.faker.middle_name_female(),
            )
        return " ".join(parts)

    def _new_snils(self) -> str:
        while True:
            number = f"{self.rng.randint(NO_CHECK_LIMIT + 1, 999_999_999):09d}"
            if number not in self._used_snils:
                self._used_snils.add(number)
                return format_snils(f"{number}{snils_checksum(number):02d}")

    def _new_tab_number(self) -> str:
        self._tab_counter += 1
        return f"ДМ-{self._tab_counter:05d}"  # ДМ — «демо»
