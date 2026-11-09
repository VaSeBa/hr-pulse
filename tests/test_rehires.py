"""Тесты шага 3.4: повторные приёмы и технические увольнения."""

import math
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import pytest

from hr_pulse.core.fields import Field
from hr_pulse.demo.export_1c import write_employees_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.convert import parse_date_columns
from hr_pulse.ingest.merge import load_mapped
from hr_pulse.ingest.reasons import COUNTS
from hr_pulse.ingest.rehires import (
    GAP,
    NEXT_HIRE,
    TECHNICAL,
    describe_rehires,
    gap_days,
    is_technical,
    mark_rehires,
)

# ---------- gap_days (задание 1) ----------


@pytest.mark.parametrize(
    ("fire", "next_hire", "expected"),
    [
        pytest.param(date(2024, 3, 31), date(2024, 4, 1), 1, id="next-day"),
        pytest.param(date(2024, 3, 31), date(2024, 3, 31), 0, id="same-day"),
        pytest.param(date(2024, 2, 28), date(2024, 3, 1), 2, id="leap-year"),
        pytest.param(date(2024, 1, 10), date(2024, 1, 5), -5, id="hire-before-fire"),
        pytest.param(None, date(2024, 4, 1), None, id="still-working"),
        pytest.param(date(2024, 3, 31), None, None, id="never-returned"),
        pytest.param(date(2024, 3, 31), math.nan, None, id="nan-from-pandas"),
    ],
)
def test_gap_days(fire, next_hire, expected):
    assert gap_days(fire, next_hire) == expected


# ---------- is_technical (задание 2) ----------


@pytest.mark.parametrize(
    ("gap", "max_gap", "expected"),
    [
        pytest.param(0, 7, True, id="same-day"),
        pytest.param(1, 7, True, id="next-day"),
        pytest.param(7, 7, True, id="border-included"),
        pytest.param(8, 7, False, id="one-day-more"),
        pytest.param(120, 7, False, id="real-return"),
        pytest.param(-3, 7, False, id="overlap-is-error-not-technical"),
        pytest.param(None, 7, False, id="no-rehire"),
        pytest.param(30, 60, True, id="user-setting"),
    ],
)
def test_is_technical(gap, max_gap, expected):
    assert is_technical(gap, max_gap) is expected


# ---------- mark_rehires на маленькой таблице ----------


def make_frame():
    return pd.DataFrame(
        {
            "tab_number": ["A1", "B1", "A2", "C1", "B2", "A3"],
            "snils": ["111", "222", "111", "333", "222", "111"],
            "hire_date": [
                date(2022, 1, 10),  # A1: первый эпизод человека 111
                date(2022, 5, 1),  # B1: человек 222
                date(2023, 4, 1),  # A2: 111 вернулся на следующий день — техническое
                date(2023, 1, 1),  # C1: человек 333, один эпизод
                date(2024, 9, 1),  # B2: 222 вернулся через полгода — настоящий возврат
                date(2024, 6, 1),  # A3: 111 вернулся ещё раз через два месяца
            ],
            "fire_date": [
                date(2023, 3, 31),
                date(2024, 3, 1),
                date(2024, 4, 1),
                None,
                None,
                None,
            ],
        }
    )


def test_next_hire_found_within_same_person():
    frame = mark_rehires(make_frame()).frame
    by_tab = dict(zip(frame["tab_number"], frame[NEXT_HIRE], strict=True))
    assert by_tab["A1"] == date(2023, 4, 1)
    assert by_tab["A2"] == date(2024, 6, 1)
    assert pd.isna(by_tab["A3"])  # последний эпизод — следующего нет
    assert pd.isna(by_tab["C1"])


def test_only_short_gap_is_technical():
    frame = mark_rehires(make_frame()).frame
    technical = dict(zip(frame["tab_number"], frame[TECHNICAL], strict=True))
    assert technical == {
        "A1": True,
        "B1": False,
        "A2": False,
        "C1": False,
        "B2": False,
        "A3": False,
    }


def test_original_order_kept():
    frame = mark_rehires(make_frame()).frame
    assert list(frame["tab_number"]) == ["A1", "B1", "A2", "C1", "B2", "A3"]


def test_counts():
    result = mark_rehires(make_frame())
    assert result.rehired_people == 2  # 111 и 222
    assert result.technical == 1
    assert result.overlaps == 0


def test_user_setting_changes_answer():
    assert mark_rehires(make_frame(), max_gap=90).technical == 2  # A1 и A2 (61 день)


def test_gap_column():
    frame = mark_rehires(make_frame()).frame
    gaps = dict(zip(frame["tab_number"], frame[GAP], strict=True))
    assert gaps["A1"] == 1
    assert gaps["A2"] == 61
    assert gaps["C1"] is None


def test_technical_removed_from_turnover():
    frame = make_frame()
    frame[COUNTS] = [True, True, True, None, None, None]  # справочник сказал «входит»
    result = mark_rehires(frame)
    counts = dict(zip(result.frame["tab_number"], result.frame[COUNTS], strict=True))
    assert counts["A1"] is False  # техническое — исключили
    assert counts["B1"] is True  # настоящий уход — остался
    assert result.excluded_from_turnover == 1


def test_overlap_counted():
    frame = pd.DataFrame(
        {
            "snils": ["111", "111"],
            "hire_date": [date(2022, 1, 1), date(2023, 1, 1)],
            "fire_date": [date(2023, 2, 1), None],  # новый приём раньше увольнения
        }
    )
    result = mark_rehires(frame)
    assert result.overlaps == 1
    assert result.technical == 0
    assert any("проверьте даты" in line for line in describe_rehires(result))


# ---------- на демо ----------


def test_demo_matches_generator(tmp_path):
    rows = FakeCompany(GeneratorConfig(people=300, seed=5)).generate()
    write_employees_report(rows, tmp_path / "e.xlsx", mislabel_fire_date=True)
    frame = load_mapped(tmp_path / "e.xlsx", {"Адрес места проживания": Field.FIRE_DATE})
    frame = parse_date_columns(frame, ["hire_date", "fire_date"])

    # Считаем ожидаемое прямо по генератору, обычным Python
    by_person = defaultdict(list)
    for row in rows:
        by_person[row.episode.snils].append(row.episode)
    expected = 0
    for episodes in by_person.values():
        episodes.sort(key=lambda e: e.hire_date)
        for current, following in zip(episodes, episodes[1:], strict=False):
            if following.hire_date - current.fire_date <= timedelta(days=7):
                expected += 1

    result = mark_rehires(frame)
    assert result.technical == expected
    assert result.technical > 0  # в демо такие есть
