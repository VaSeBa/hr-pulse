"""Сопоставление колонок: какая колонка выгрузки — какое поле шаблона.

В разных отчётах 1С одно и то же поле называется по-разному: «Таб. номер»,
«Табельный номер (с префиксами)», «Сотрудник.Таб. номер». Модуль узнаёт поле
по названию колонки, а чего не узнал — честно показывает человеку.
"""

from dataclasses import dataclass, field

import pandas as pd

from hr_pulse.core.fields import REQUIRED_FIELDS, TEMPLATE, Field, FieldKind, FieldSpec
from hr_pulse.core.text import normalize_header
from hr_pulse.ingest.convert import date_share

DATE_SUGGEST_SHARE = 0.9  # колонку предлагаем как дату, если ≥ 90% значений — даты


def candidate_names(spec: FieldSpec) -> tuple[str, ...]:
    """Все известные названия поля: название из шаблона и синонимы — нормализованные."""
    return (normalize_header(spec.title), *spec.synonyms)


def contains_phrase(text: str, phrase: str) -> bool:
    """Есть ли в тексте фраза ЦЕЛЫМИ словами: «дата приема» есть в «прием дата приема»,
    а «дата» в «датах» — нет."""
    return f" {phrase} " in f" {text} "


def match_column(header: str) -> Field | None:
    """Какое поле шаблона прячется за названием колонки; не узнали — None.

    1) точное совпадение с названием или синонимом поля;
    2) иначе — самая ДЛИННАЯ известная фраза, входящая в название целыми словами
       («Подразделение.Подразделение верхнего уровня…» — это верхний уровень,
       а не просто «подразделение»).
    """
    name = normalize_header(header)
    for spec in TEMPLATE:
        if name in candidate_names(spec):
            return spec.field

    best_field = None
    best_length = 0
    for spec in TEMPLATE:
        for candidate in candidate_names(spec):
            if contains_phrase(name, candidate) and len(candidate) > best_length:
                best_field = spec.field
                best_length = len(candidate)
    return best_field


def missing_required(found: set[Field]) -> list[Field]:
    """Обязательные поля, которых нет среди найденных, — в порядке шаблона."""
    result = []
    for spec in TEMPLATE:
        if spec.field in REQUIRED_FIELDS and spec.field not in found:
            result.append(spec.field)

    return result


@dataclass(frozen=True)
class ColumnMapping:
    """Итог сопоставления."""

    fields: dict[str, Field]  # название колонки → поле шаблона
    unknown: list[str]  # колонки, которые не узнали (в аналитику не идут)
    duplicates: list[str]  # колонки, чьё поле уже занято более ранней колонкой
    missing: list[Field]  # обязательные поля, для которых колонки нет
    suggestions: dict[Field, list[str]] = field(default_factory=dict)  # подсказки по пропускам


def map_columns(frame: pd.DataFrame, overrides: dict[str, Field] | None = None) -> ColumnMapping:
    """Сопоставить колонки таблицы с полями шаблона.

    overrides — решения человека: «колонка X — это поле Y». Они главнее автоматики:
    так пользователь скажет, что «Адрес места проживания» на самом деле дата увольнения.
    """
    overrides = overrides or {}
    fields: dict[str, Field] = {}
    unknown: list[str] = []
    duplicates: list[str] = []

    for column in frame.columns:
        name = str(column)
        found = overrides.get(name) or match_column(name)
        if found is None:
            unknown.append(name)
        elif found in fields.values():
            duplicates.append(name)
        else:
            fields[name] = found

    missing = missing_required(set(fields.values()))
    suggestions = suggest_dates(frame, missing, unknown)
    return ColumnMapping(fields, unknown, duplicates, missing, suggestions)


def suggest_dates(
    frame: pd.DataFrame, missing: list[Field], unknown: list[str]
) -> dict[Field, list[str]]:
    """Для ненайденных полей-дат — неузнанные колонки, которые похожи на даты."""
    date_like = [name for name in unknown if date_share(frame[name]) >= DATE_SUGGEST_SHARE]
    result: dict[Field, list[str]] = {}
    for missing_field in missing:
        spec = next(spec for spec in TEMPLATE if spec.field == missing_field)
        if spec.kind is FieldKind.DATE and date_like:
            result[missing_field] = date_like
    return result


def apply_mapping(frame: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    """Таблица только из узнанных колонок, колонки названы именами полей (hire_date…)."""
    renamed = frame[list(mapping.fields)].rename(columns=mapping.fields)
    renamed.columns = [str(name) for name in renamed.columns]
    return renamed
