"""Тесты шага 7.2: стаж уволенных и ранняя текучесть."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.analytics.tenure import (
    LABELS,
    LAST_BUCKET,
    bar,
    bucket_for,
    by_department,
    count_buckets,
    describe_buckets,
    dismissed_rows,
    early_share,
    tenure_days,
)
from hr_pulse.db.storage import connect, upsert_episodes

# ---------- пример: bucket_for ----------


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        pytest.param(1, "до 1 мес", id="one-day"),
        pytest.param(30, "до 1 мес", id="border-30"),
        pytest.param(31, "1–3 мес", id="day-31"),
        pytest.param(91, "1–3 мес", id="border-91"),
        pytest.param(200, "6–12 мес", id="half-year"),
        pytest.param(1095, "1–3 года", id="border-3-years"),
        pytest.param(5000, LAST_BUCKET, id="veteran"),
    ],
)
def test_bucket_for(days, expected):
    assert bucket_for(days) == expected


# ---------- Задача 1: tenure_days и count_buckets ----------


@pytest.mark.parametrize(
    ("hire", "fire", "expected"),
    [
        pytest.param(date(2026, 9, 1), date(2026, 9, 1), 1, id="same-day"),
        pytest.param(date(2026, 9, 1), date(2026, 9, 30), 30, id="month"),
        pytest.param(date(2025, 1, 1), date(2025, 12, 31), 365, id="year"),
    ],
)
def test_tenure_days(hire, fire, expected):
    assert tenure_days(hire, fire) == expected


def test_count_buckets():
    counts = count_buckets([10, 20, 45, 400, 5000])
    assert counts["до 1 мес"] == 2
    assert counts["1–3 мес"] == 1
    assert counts["1–3 года"] == 1
    assert counts[LAST_BUCKET] == 1


def test_count_buckets_keeps_empty_buckets():
    counts = count_buckets([45])
    assert list(counts) == LABELS  # все корзины, по порядку
    assert counts["до 1 мес"] == 0


def test_count_buckets_nothing():
    assert count_buckets([]) == {label: 0 for label in LABELS}


def test_count_buckets_total():
    days = [1, 30, 31, 91, 92, 182, 183, 365, 366, 1095, 1096]
    assert sum(count_buckets(days).values()) == len(days)


# ---------- Задача 2: early_share ----------


def test_early_share():
    counts = count_buckets([10, 45, 400, 5000])  # 2 ранних из 4
    assert early_share(counts) == pytest.approx(50.0)


def test_early_share_none_early():
    assert early_share(count_buckets([400, 5000])) == 0


def test_early_share_all_early():
    assert early_share(count_buckets([5, 60])) == pytest.approx(100.0)


def test_early_share_nobody():
    assert early_share(count_buckets([])) is None


# ---------- готовые помощники ----------


def test_bar():
    assert bar(25.0) == "█" * 10
    assert bar(0) == ""


def test_describe_buckets():
    lines = describe_buckets(count_buckets([10, 45, 45, 400]))
    assert len(lines) == len(LABELS)
    assert lines[1].split() == ["1–3", "мес", "2", "50,0", "%", "█" * 20]


def test_describe_buckets_empty():
    lines = describe_buckets(count_buckets([]))
    assert lines[0].split() == ["до", "1", "мес", "0", "0,0", "%"]


def test_by_department():
    rows = [("ОП Северное", 10), ("ОП Восточное", 400), ("ОП Северное", 45)]
    assert by_department(rows) == {"ОП Северное": [10, 45], "ОП Восточное": [400]}


def test_dismissed_rows():
    conn = connect(":memory:")
    episodes = pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4"],
            "snils": ["112-233-445 95"] * 4,
            "top_department": ["ОП Северное", None, "ОП Северное", "ОП Северное"],
            "hire_date": [date(2026, 9, 1), date(2024, 9, 1), date(2026, 9, 1), date(2026, 9, 1)],
            "fire_date": [
                date(2026, 9, 15),
                date(2026, 9, 30),
                date(2026, 9, 20),
                date(2026, 10, 2),
            ],
            "counts_in_turnover": [True, True, False, True],  # №3 — не входит, №4 — октябрь
        }
    )
    upsert_episodes(conn, episodes)
    assert sorted(dismissed_rows(conn, "2026-09", "2026-09")) == [
        ("(подразделение не указано)", 760),
        ("ОП Северное", 15),
    ]
    conn.close()
