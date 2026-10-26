"""Тесты для hr_pulse.core.fields."""

from hr_pulse.core.fields import (
    PERSONAL_DATA_FIELDS,
    REQUIRED_FIELDS,
    TEMPLATE,
    Field,
    FieldKind,
    get_spec,
)
from hr_pulse.core.text import normalize_header


def test_every_field_described_once():
    described = [spec.field for spec in TEMPLATE]
    assert sorted(described) == sorted(Field)  # каждое поле есть, и ровно один раз


def test_required_fields():
    assert {
        Field.TAB_NUMBER,
        Field.POSITION,
        Field.DEPARTMENT,
        Field.HIRE_DATE,
        Field.FIRE_DATE,
        Field.SNILS,
    } == REQUIRED_FIELDS


def test_full_name_is_optional_personal_data():
    # ФИО не нужно для аналитики — минимизация ПДн: можно вообще не загружать
    spec = get_spec(Field.FULL_NAME)
    assert spec.required is False
    assert spec.personal_data is True


def test_personal_data_fields():
    assert {Field.FULL_NAME, Field.SNILS} == PERSONAL_DATA_FIELDS


def test_dates_have_date_kind():
    assert get_spec(Field.HIRE_DATE).kind is FieldKind.DATE
    assert get_spec(Field.FIRE_DATE).kind is FieldKind.DATE


def test_synonyms_are_already_normalized():
    # Синонимы сравниваются с нормализованными заголовками — значит, сами должны быть нормализованы
    for spec in TEMPLATE:
        for synonym in spec.synonyms:
            assert synonym == normalize_header(synonym), f"{spec.field}: {synonym!r}"


def test_field_is_a_string():
    # StrEnum: элемент перечисления можно использовать как обычную строку
    assert Field.HIRE_DATE == "hire_date"
