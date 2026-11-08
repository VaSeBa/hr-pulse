"""Справочник причин увольнения: какие причины входят в учётную текучесть, а какие нет.

Справочник ведёт компания (файл Excel: «Наименование» и «Учёт в текучести» —
«Входит» / «Не входит»). Программа не решает за HR, что считать текучестью:
она берёт решение из справочника и показывает причины, которых в нём нет.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hr_pulse.core.fields import Field
from hr_pulse.core.formats_1c import is_blank
from hr_pulse.core.text import normalize_header
from hr_pulse.ingest.mapping import contains_phrase
from hr_pulse.ingest.reader import read_1c_table

INCLUDED = "входит"
EXCLUDED = "не входит"
NAME_WORDS = ("наименование", "причина")  # как может называться колонка с причиной
STATUS_WORDS = ("текучести", "текучесть")  # как может называться колонка с признаком
COUNTS = "counts_in_turnover"  # новая колонка: True / False / None


def reason_key(value: object) -> str | None:
    """Причина к виду для сравнения: «ПЕРЕЕЗД В ДРУГОЙ ГОРОД» и «Переезд в другой город»
    дают один ключ. Пустая ячейка → None."""
    if is_blank(value):
        return None
    return normalize_header(str(value))


def parse_status(value: object) -> bool:
    """Признак из справочника: «Входит» → True, «Не входит» → False, иначе — ValueError."""
    key = reason_key(value)
    if key == INCLUDED:
        return True
    if key == EXCLUDED:
        return False
    raise ValueError(f"непонятный признак учёта в текучести: {value!r}")


@dataclass(frozen=True)
class ReasonBook:
    """Справочник в памяти: ключ причины → входит ли она в текучесть."""

    statuses: dict[str, bool]

    def counts(self, reason: object) -> bool | None:
        """Входит ли причина в текучесть; нет причины или её нет в справочнике — None."""
        key = reason_key(reason)
        if key is None:
            return None
        return self.statuses.get(key)


def find_column(frame: pd.DataFrame, words: tuple[str, ...]) -> str:
    """Первая колонка, в названии которой есть одно из слов (целыми словами)."""
    for column in frame.columns:
        name = normalize_header(str(column))
        if any(contains_phrase(name, word) for word in words):
            return column
    raise ValueError(f"в справочнике нет колонки со словом: {' / '.join(words)}")


def load_reference(path: Path) -> ReasonBook:
    """Прочитать справочник причин из Excel."""
    frame = read_1c_table(path).frame
    name_column = find_column(frame, NAME_WORDS)
    status_column = find_column(frame, STATUS_WORDS)

    statuses: dict[str, bool] = {}
    for name, status in zip(frame[name_column], frame[status_column], strict=True):
        key = reason_key(name)
        if key is None:
            continue  # пустая строка справочника — пропускаем
        try:
            statuses[key] = parse_status(status)
        except ValueError as error:
            raise ValueError(f"справочник, причина «{name}»: {error}") from error
    return ReasonBook(statuses)


@dataclass(frozen=True)
class ReasonsSummary:
    """Итог разметки причин."""

    frame: pd.DataFrame  # таблица с новой колонкой counts_in_turnover
    included: int  # увольнений, которые входят в текучесть
    excluded: int  # увольнений, которые не входят
    without_reason: int  # уволен, а причины нет
    unknown: dict[str, int]  # причины, которых нет в справочнике → сколько раз встретились


def apply_reference(frame: pd.DataFrame, book: ReasonBook) -> ReasonsSummary:
    """Добавить колонку «входит ли увольнение в текучесть» и посчитать итоги."""
    reason = Field.FIRE_REASON.value
    result = frame.copy()
    result[COUNTS] = result[reason].map(book.counts)

    fired = result[Field.FIRE_DATE.value].notna()
    has_reason = result[reason].notna()
    unknown_mask = has_reason & result[COUNTS].isna()

    return ReasonsSummary(
        frame=result,
        included=int(result[COUNTS].eq(True).sum()),
        excluded=int(result[COUNTS].eq(False).sum()),
        without_reason=int((fired & ~has_reason).sum()),
        unknown=result.loc[unknown_mask, reason].value_counts().to_dict(),
    )


def describe_reasons(summary: ReasonsSummary) -> list[str]:
    """Итог разметки строками. Причины — это не ПДн, их можно показывать."""
    lines = [
        f"Входят в текучесть: {summary.included}",
        f"Не входят в текучесть: {summary.excluded}",
    ]
    if summary.unknown:
        lines.append("Причин нет в справочнике — добавьте их и укажите «Входит» / «Не входит»:")
        for name, count in summary.unknown.items():
            lines.append(f"   «{name}» — {count}")
    return lines
