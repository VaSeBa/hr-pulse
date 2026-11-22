"""Тесты шага 6.4: приёмочный тест против своего отчёта."""

from datetime import date, datetime

import pandas as pd
import pytest
from openpyxl import Workbook

from hr_pulse.db.ssch import set_ssch
from hr_pulse.db.storage import connect, upsert_episodes
from hr_pulse.quality.acceptance import (
    DISMISSED,
    ORG,
    RATE,
    SSCH,
    Check,
    Expected,
    compare,
    describe_check,
    details,
    is_match,
    match_header,
    parse_number,
    read_expected,
    summary,
    tolerance_for,
    write_template,
)

# ---------- Задача 1: is_match ----------


@pytest.mark.parametrize(
    ("ours", "theirs", "tolerance", "expected"),
    [
        pytest.param(7, 7, 0, True, id="count-equal"),
        pytest.param(7, 9, 0, False, id="count-differs"),
        pytest.param(9, 7, 0, False, id="count-more"),
        pytest.param(255.0, 253.7, 7.6, True, id="ssch-within"),
        pytest.param(5.92, 6.62, 0.5, False, id="rate-outside"),
        pytest.param(6.36, 5.86, 0.5, True, id="exactly-on-border"),
        pytest.param(None, 7, 0, False, id="nothing-to-compare"),
        pytest.param(0, 0, 0, True, id="zeros"),
    ],
)
def test_is_match(ours, theirs, tolerance, expected):
    assert is_match(ours, theirs, tolerance) is expected


# ---------- Задача 2: summary ----------


def check(ok: bool) -> Check:
    return Check("2026-09", "ОП Северное", DISMISSED, 7, 7 if ok else 9, ok)


def test_summary_all_ok():
    assert summary([check(True), check(True)]) == "Совпало 2 из 2 — приёмка пройдена"


def test_summary_with_failures():
    checks = [check(True), check(False), check(True), check(False)]
    assert summary(checks) == "Совпало 2 из 4, расхождений: 2"


def test_summary_all_failed():
    assert summary([check(False)]) == "Совпало 0 из 1, расхождений: 1"


def test_summary_empty():
    assert summary([]) == "В эталоне нет ни одной проверки"


# ---------- готовые помощники ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("Месяц", "month", id="month"),
        pytest.param("ОП", "department", id="op"),
        pytest.param("Уволено, чел.", DISMISSED, id="dismissed-with-unit"),
        pytest.param("ССЧ", SSCH, id="ssch"),
        pytest.param("Среднесписочная численность", SSCH, id="ssch-long"),
        pytest.param("Кт, %", RATE, id="rate"),
        pytest.param("Опыт", None, id="not-op"),
        pytest.param("Примечание", None, id="other"),
    ],
)
def test_match_header(text, expected):
    assert match_header(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("549,5", 549.5, id="comma"),
        pytest.param("1 545", 1545.0, id="space"),
        pytest.param("6,36 %", 6.36, id="percent-sign"),
        pytest.param(None, None, id="empty"),
    ],
)
def test_parse_number(value, expected):
    assert parse_number(value) == expected


def test_parse_number_bad():
    with pytest.raises(ValueError, match="не число"):
        parse_number("много")


def test_tolerance_for():
    assert tolerance_for(DISMISSED, 9) == 0
    assert tolerance_for(SSCH, 200.0) == pytest.approx(6.0)
    assert tolerance_for(RATE, 3.5) == 0.5


def test_describe_check():
    line = describe_check(Check("2026-09", "ОП Северное", DISMISSED, 7, 9, False))
    assert line == "✗ 09.2026 · ОП Северное · Уволено: отчёт 9, HR Pulse 7"


# ---------- чтение эталона ----------


def make_expected(path, rows, rate_format=None):
    wb = Workbook()
    ws = wb.active
    ws.append(["Текучесть по подразделениям"])
    ws.append([])
    ws.append(["Месяц", "Подразделение", "Уволено", "ССЧ", "Кт, %"])
    for row in rows:
        ws.append(row)
        if rate_format:
            ws.cell(row=ws.max_row, column=5).number_format = rate_format
    wb.save(path)


def test_read_expected(tmp_path):
    path = tmp_path / "e.xlsx"
    make_expected(
        path, [["09.2026", "ОП Северное", 7, 255, 2.75], ["09.2026", "Итого", 18, None, None]]
    )
    rows, errors = read_expected(path)
    assert errors == []
    assert rows == [
        Expected(4, "2026-09", "ОП Северное", {DISMISSED: 7, SSCH: 255, RATE: 2.75}),
        Expected(5, "2026-09", ORG, {DISMISSED: 18}),
    ]


def test_read_expected_rate_as_share(tmp_path):
    path = tmp_path / "share.xlsx"
    make_expected(path, [["09.2026", "ОП Северное", 7, 255, 0.0275]], rate_format="0.00%")
    rows, _ = read_expected(path)
    assert rows[0].values[RATE] == pytest.approx(2.75)


def test_read_expected_bad_rows(tmp_path):
    path = tmp_path / "bad.xlsx"
    make_expected(path, [["13.2026", "ОП", 1], ["09.2026", "ОП", None], [None, None, None]])
    rows, errors = read_expected(path)
    assert rows == []
    assert errors == [
        "строка 4: месяц пишется так: 10.2026, а не '13.2026'",
        "строка 5: не указано число уволенных",
    ]


def test_template_is_readable(tmp_path):
    path = tmp_path / "blank.xlsx"
    write_template(path)
    assert read_expected(path) == ([], [])


# ---------- сверка с базой ----------


@pytest.fixture
def conn():
    connection = connect(":memory:")
    episodes = pd.DataFrame(
        {
            "tab_number": ["1", "2", "3", "4"],
            "snils": ["112-233-445 95"] * 4,
            "top_department": ["ОП Северное", "ОП Северное", "ОП Восточное", "ОП Северное"],
            "hire_date": [date(2024, 1, 10)] * 4,
            "fire_date": [date(2026, 9, 10), date(2026, 9, 20), None, date(2026, 9, 25)],
            "fire_reason": ["Оплата труда", "Несоблюдение ПВТР", None, "Оплата труда"],
            "counts_in_turnover": [True, False, None, True],
        }
    )
    upsert_episodes(connection, episodes)
    set_ssch(connection, "2026-09", 3.0, now=datetime(2026, 11, 19))
    yield connection
    connection.close()


def test_compare(conn):
    expected = [
        Expected(4, "2026-09", "ОП Северное", {DISMISSED: 3}),  # в отчёте посчитали ПВТР
        Expected(5, "2026-09", ORG, {DISMISSED: 2, SSCH: 3.0, RATE: 66.67}),
        Expected(6, "2026-09", "ОП Неизвестное", {SSCH: 10.0, DISMISSED: 0}),
    ]
    checks = compare(conn, expected)
    assert [(c.department, c.metric, c.ours, c.ok) for c in checks] == [
        ("ОП Северное", DISMISSED, 2, False),
        (ORG, DISMISSED, 2, True),
        (ORG, SSCH, 3.0, True),
        (ORG, RATE, pytest.approx(66.667, rel=1e-3), True),
        ("ОП Неизвестное", SSCH, None, False),
        ("ОП Неизвестное", DISMISSED, 0, True),
    ]


def test_details(conn):
    assert details(conn, "2026-09", "ОП Северное") == [
        "Оплата труда — 2 (входит)",
        "Несоблюдение ПВТР — 1 (не входит)",
    ]


def test_details_unknown_department(conn):
    assert details(conn, "2026-09", "ОП Неизвестное") == []
