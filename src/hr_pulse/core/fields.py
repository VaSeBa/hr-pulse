"""Поля шаблона: какие данные о сотрудниках приложение понимает и как их искать в выгрузках."""

from dataclasses import dataclass
from enum import StrEnum


class Field(StrEnum):
    """Поле шаблона. Значение — внутреннее имя, оно же имя колонки в базе данных."""

    TAB_NUMBER = "tab_number"
    FULL_NAME = "full_name"
    POSITION = "position"
    DEPARTMENT = "department"
    TOP_DEPARTMENT = "top_department"
    FUNCTIONAL_BLOCK = "functional_block"
    FUNCTIONAL_SUBORDINATION = "functional_subordination"
    STAFF_CATEGORY = "staff_category"
    HIRE_DATE = "hire_date"
    FIRE_DATE = "fire_date"
    SNILS = "snils"
    FIRE_REASON = "fire_reason"


class FieldKind(StrEnum):
    """Тип значения в поле — от него зависит, как значение разбирать и проверять."""

    TEXT = "text"
    DATE = "date"
    SNILS = "snils"


@dataclass(frozen=True)
class FieldSpec:
    """Описание одного поля шаблона."""

    field: Field
    title: str  # как поле называется для пользователя
    kind: FieldKind
    required: bool  # без этой колонки аналитику не построить
    personal_data: bool  # ПДн по 152-ФЗ: маскировать при экспорте
    synonyms: tuple[str, ...] = ()  # как колонка может называться в выгрузках


TEMPLATE: tuple[FieldSpec, ...] = (
    FieldSpec(
        Field.TAB_NUMBER,
        "Табельный номер",
        FieldKind.TEXT,
        required=True,
        personal_data=False,
        synonyms=("таб номер", "табельный номер с префиксами", "сотрудник таб номер"),
    ),
    FieldSpec(
        Field.FULL_NAME,
        "ФИО",
        FieldKind.TEXT,
        required=False,
        personal_data=True,
        synonyms=("сотрудник", "фамилия имя отчество", "работник"),
    ),
    FieldSpec(Field.POSITION, "Должность", FieldKind.TEXT, required=True, personal_data=False),
    FieldSpec(
        Field.DEPARTMENT, "Подразделение", FieldKind.TEXT, required=True, personal_data=False
    ),
    FieldSpec(
        Field.TOP_DEPARTMENT,
        "Подразделение верхнего уровня",
        FieldKind.TEXT,
        required=False,
        personal_data=False,
        synonyms=("подразделение верхнего уровня для отчетов",),
    ),
    FieldSpec(
        Field.FUNCTIONAL_BLOCK,
        "Функциональный блок",
        FieldKind.TEXT,
        required=False,
        personal_data=False,
    ),
    FieldSpec(
        Field.FUNCTIONAL_SUBORDINATION,
        "Функциональное подчинение",
        FieldKind.TEXT,
        required=False,
        personal_data=False,
    ),
    FieldSpec(
        Field.STAFF_CATEGORY,
        "Категория персонала",
        FieldKind.TEXT,
        required=False,
        personal_data=False,
        synonyms=("подкатегория персонала",),
    ),
    FieldSpec(
        Field.HIRE_DATE,
        "Дата приёма",
        FieldKind.DATE,
        required=True,
        personal_data=False,
        synonyms=("дата приема", "прием на работу дата приема"),
    ),
    FieldSpec(
        Field.FIRE_DATE,
        "Дата увольнения",
        FieldKind.DATE,
        required=True,
        personal_data=False,
        synonyms=("увольнение дата увольнения",),
    ),
    FieldSpec(Field.SNILS, "СНИЛС", FieldKind.SNILS, required=True, personal_data=True),
    FieldSpec(
        Field.FIRE_REASON,
        "Причина увольнения",
        FieldKind.TEXT,
        required=False,
        personal_data=False,
        synonyms=("причина по мнению hr",),
    ),
)


def get_spec(field: Field) -> FieldSpec:
    """Возвращает описание поля шаблона."""
    for spec in TEMPLATE:
        if spec.field == field:
            return spec
    raise KeyError(f"поле {field} не описано в шаблоне")


REQUIRED_FIELDS: frozenset[Field] = frozenset(spec.field for spec in TEMPLATE if spec.required)
PERSONAL_DATA_FIELDS: frozenset[Field] = frozenset(
    spec.field for spec in TEMPLATE if spec.personal_data
)
