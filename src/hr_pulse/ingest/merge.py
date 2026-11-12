"""Объединение отчётов: к эпизодам из «Личных данных сотрудников» добавить причины увольнения.

Связываем по табельному номеру — он есть в обоих отчётах и однозначно указывает
на эпизод (решение из шага 1.3). Это как ВПР или «Объединить запросы» в Power Query:
слева — список сотрудников, справа — справочник причин, ключ — табельный номер.

Запуск: uv run python -m hr_pulse.ingest.merge сотрудники.xlsx причины.xlsx
        [--fire-date "Адрес места проживания"] [--reference справочник.xlsx] [--rehire-days 7]
Печатает только числа — без ФИО, СНИЛС и табельных номеров.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hr_pulse.core.fields import Field, get_spec
from hr_pulse.core.formats_1c import is_blank
from hr_pulse.core.snils import clean_snils
from hr_pulse.ingest.convert import parse_date_columns
from hr_pulse.ingest.mapping import apply_mapping, map_columns
from hr_pulse.ingest.reader import read_1c_table
from hr_pulse.ingest.reasons import apply_reference, describe_reasons, load_reference
from hr_pulse.ingest.rehires import REHIRE_GAP_DAYS, describe_rehires, mark_rehires

KEY = Field.TAB_NUMBER.value  # «tab_number» — колонка, по которой связываем
EMPLOYEES_NEED = (Field.TAB_NUMBER, Field.SNILS, Field.HIRE_DATE, Field.FIRE_DATE)
REASONS_NEED = (Field.TAB_NUMBER, Field.FIRE_DATE, Field.FIRE_REASON)
REASON_DATE = "reason_fire_date"  # дата увольнения по отчёту причин — для сверки


def clean_tab_number(value: object) -> str | None:
    """Табельный номер к единому виду: без пробелов по краям и внутри, заглавными.
    " дм-00012 " → "ДМ-00012"; пустая ячейка → None.
    """
    if is_blank(value):
        return None
    return str(value).replace("\xa0", "").replace(" ", "").upper()


def load_mapped(path: Path, overrides: dict[str, Field] | None = None) -> pd.DataFrame:
    """Прочитать выгрузку и привести колонки к именам полей (шаги 2.1–3.1 одной функцией)."""
    frame = read_1c_table(path).frame
    return apply_mapping(frame, map_columns(frame, overrides))


def require_columns(frame: pd.DataFrame, need: tuple[Field, ...], report: str) -> None:
    """Проверить, что нужные поля есть; нет — ValueError с понятным списком."""
    absent = [get_spec(f).title for f in need if f.value not in frame.columns]
    if absent:
        raise ValueError(f"в отчёте «{report}» не найдено: {', '.join(absent)}")


def date_mismatches(frame: pd.DataFrame) -> int:
    """Сколько строк, где отчёт причин знает дату увольнения, а она не совпадает с основной."""
    has_reason_date = frame[REASON_DATE].notna()
    differs = frame[Field.FIRE_DATE.value] != frame[REASON_DATE]
    return int((has_reason_date & differs).sum())


@dataclass(frozen=True)
class MergeResult:
    """Объединённая таблица и всё, что при объединении показалось подозрительным."""

    frame: pd.DataFrame  # эпизоды с колонкой fire_reason, без ФИО
    reasons_total: int  # строк в отчёте причин
    duplicate_reasons: int  # повторы одного табельного номера в отчёте причин
    orphan_reasons: int  # причины, для которых нет эпизода в списке сотрудников
    date_mismatches: int  # даты увольнения в двух отчётах расходятся
    fired_without_reason: int  # уволен, а причины нет


def merge_reasons(employees: pd.DataFrame, reasons: pd.DataFrame) -> MergeResult:
    """Добавить к эпизодам причины увольнения по табельному номеру."""
    require_columns(employees, EMPLOYEES_NEED, "Сотрудники")
    require_columns(reasons, REASONS_NEED, "Причины увольнений")

    # ФИО для аналитики не нужно — выбрасываем сразу (минимизация ПДн, 152-ФЗ)
    left = employees.drop(columns=[Field.FULL_NAME.value], errors="ignore").copy()
    left[KEY] = left[KEY].map(clean_tab_number)
    left[Field.SNILS.value] = left[Field.SNILS.value].map(clean_snils)  # один человек — один вид
    left = parse_date_columns(left, [Field.HIRE_DATE.value, Field.FIRE_DATE.value])

    right = reasons[[KEY, Field.FIRE_DATE.value, Field.FIRE_REASON.value]].copy()
    right[KEY] = right[KEY].map(clean_tab_number)
    right = parse_date_columns(right, [Field.FIRE_DATE.value])
    right = right.rename(columns={Field.FIRE_DATE.value: REASON_DATE})

    repeated = right[KEY].duplicated(keep="first")  # True у второго и дальше повторов
    right = right[~repeated]  # ~ — «не»: оставить только первые вхождения

    orphans = ~right[KEY].isin(left[KEY])  # табельного номера нет среди эпизодов
    merged = left.merge(right, on=KEY, how="left")  # how="left" — все эпизоды остаются

    mismatches = date_mismatches(merged)
    fired = merged[Field.FIRE_DATE.value].notna()
    no_reason = merged[Field.FIRE_REASON.value].isna()

    return MergeResult(
        frame=merged.drop(columns=[REASON_DATE]),
        reasons_total=len(reasons),
        duplicate_reasons=int(repeated.sum()),
        orphan_reasons=int(orphans.sum()),
        date_mismatches=mismatches,
        fired_without_reason=int((fired & no_reason).sum()),
    )


def describe_merge(result: MergeResult) -> list[str]:
    """Итог объединения строками — только числа."""
    frame = result.frame
    fired = int(frame[Field.FIRE_DATE.value].notna().sum())
    linked = int(frame[Field.FIRE_REASON.value].notna().sum())
    return [
        f"Эпизодов: {len(frame)}, из них уволены: {fired}",
        f"Строк в отчёте причин: {result.reasons_total}, привязано к эпизодам: {linked}",
        f"Повторы табельного номера в отчёте причин: {result.duplicate_reasons}",
        f"Причины без эпизода в списке сотрудников: {result.orphan_reasons}",
        f"Даты увольнения в отчётах расходятся: {result.date_mismatches}",
        f"Уволены без причины: {result.fired_without_reason} "
        "(проверьте период отчёта причин — он может начинаться позже)",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Объединить сотрудников и причины увольнений")
    parser.add_argument("employees", type=Path, help="выгрузка «Личные данные сотрудников»")
    parser.add_argument("reasons", type=Path, help="выгрузка «Причины увольнений»")
    parser.add_argument("--fire-date", help="колонка с датой увольнения, если не узналась сама")
    parser.add_argument("--reference", type=Path, help="справочник причин «Входит / Не входит»")
    parser.add_argument(
        "--rehire-days",
        type=int,
        default=REHIRE_GAP_DAYS,
        help="перерыв в днях до нового приёма, который считаем техническим (%(default)s)",
    )
    args = parser.parse_args()

    overrides = {args.fire_date: Field.FIRE_DATE} if args.fire_date else None
    try:
        employees = load_mapped(args.employees, overrides)
        result = merge_reasons(employees, load_mapped(args.reasons))
        book = load_reference(args.reference) if args.reference else None
    except ValueError as error:
        print(f"Не получилось объединить: {error}")
        print("Какие колонки узнались, покажет: uv run python -m hr_pulse.ingest файл.xlsx")
        raise SystemExit(1) from error
    for line in describe_merge(result):
        print(line)
    frame = result.frame
    if book is not None:
        reasons = apply_reference(frame, book)
        frame = reasons.frame
        for line in describe_reasons(reasons):
            print(line)
    rehires = mark_rehires(frame, args.rehire_days)
    for line in describe_rehires(rehires, args.rehire_days):
        print(line)


if __name__ == "__main__":
    main()
