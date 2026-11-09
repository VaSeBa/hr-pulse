"""Повторные приёмы и технические увольнения.

Человек уволен 31.03 и принят снова 01.04 — это не текучесть, а переоформление:
закрылся объект, сменилось обособленное подразделение, перевели «через увольнение».
Такие эпизоды мы не склеиваем (каждый табельный номер остаётся), а ОТМЕЧАЕМ —
и не считаем их увольнения текучестью.

Сколько дней между увольнением и новым приёмом считать «техническим» перерывом,
решает пользователь (по умолчанию — REHIRE_GAP_DAYS).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from hr_pulse.core.fields import Field
from hr_pulse.core.formats_1c import is_blank
from hr_pulse.ingest.reasons import COUNTS

REHIRE_GAP_DAYS = 7  # перерыв до 7 дней включительно — техническое увольнение
NEXT_HIRE = "next_hire_date"  # дата следующего приёма этого же человека
GAP = "rehire_gap_days"  # дней от увольнения до следующего приёма
TECHNICAL = "is_technical"  # True — техническое увольнение


def gap_days(fire: date | None, next_hire: date | None) -> int | None:
    """Дней от увольнения до следующего приёма; нет одной из дат — None."""
    if is_blank(fire) or is_blank(next_hire):
        return None
    return (next_hire - fire).days


def is_technical(gap: int | None, max_gap: int) -> bool:
    """Техническое ли увольнение: следующий приём через 0…max_gap дней."""
    if gap is None:
        return False
    return 0 <= gap <= max_gap


@dataclass(frozen=True)
class RehireResult:
    """Таблица с отметками и итоги."""

    frame: pd.DataFrame  # + колонки next_hire_date, rehire_gap_days, is_technical
    rehired_people: int  # людей, у которых больше одного эпизода
    technical: int  # технических увольнений
    excluded_from_turnover: int  # по справочнику «входило», а стало «не входит»
    overlaps: int  # новый приём РАНЬШЕ увольнения — ошибка в датах


def mark_rehires(frame: pd.DataFrame, max_gap: int = REHIRE_GAP_DAYS) -> RehireResult:
    """Отметить технические увольнения: тот же СНИЛС снова принят в течение max_gap дней."""
    snils = Field.SNILS.value
    hire = Field.HIRE_DATE.value
    fire = Field.FIRE_DATE.value

    result = frame.sort_values([snils, hire])  # эпизоды каждого человека — подряд, по порядку
    result[NEXT_HIRE] = result.groupby(snils)[hire].shift(-1)  # дата приёма из следующей строки

    gaps = [gap_days(f, n) for f, n in zip(result[fire], result[NEXT_HIRE], strict=True)]
    result[GAP] = pd.Series(gaps, index=result.index, dtype="object")
    result[TECHNICAL] = [is_technical(gap, max_gap) for gap in gaps]

    excluded = 0
    if COUNTS in result.columns:  # справочник причин уже применён (шаг 3.3)
        was_counted = result[COUNTS].eq(True) & result[TECHNICAL]
        excluded = int(was_counted.sum())
        result.loc[result[TECHNICAL], COUNTS] = False  # техническое — не текучесть

    episodes_per_person = result[snils].value_counts()
    return RehireResult(
        frame=result.sort_index(),  # вернуть исходный порядок строк
        rehired_people=int((episodes_per_person > 1).sum()),
        technical=int(result[TECHNICAL].sum()),
        excluded_from_turnover=excluded,
        overlaps=sum(1 for gap in gaps if gap is not None and gap < 0),
    )


def describe_rehires(result: RehireResult, max_gap: int = REHIRE_GAP_DAYS) -> list[str]:
    """Итог строками — только числа."""
    lines = [
        f"Людей с повторным приёмом: {result.rehired_people}",
        f"Технических увольнений (новый приём в течение {max_gap} дн.): {result.technical}",
    ]
    if result.excluded_from_turnover:
        lines.append(
            f"   из них по справочнику входили в текучесть — исключены: "
            f"{result.excluded_from_turnover}"
        )
    if result.overlaps:
        lines.append(f"Новый приём раньше увольнения — проверьте даты: {result.overlaps}")
    return lines
