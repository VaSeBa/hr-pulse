"""Тесты шага 6.2: загрузка без причин не стирает причины и отметки «Входит»."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.db.storage import LoadStats, connect, update_clause, upsert_episodes, with_kept


def test_update_clause_keep():
    columns = ("tab_number", "fire_date", "fire_reason")
    assert update_clause(columns, keep=("fire_reason",)) == (
        "fire_date = excluded.fire_date, fire_reason = COALESCE(excluded.fire_reason, fire_reason)"
    )


def test_update_clause_without_keep_is_old_behaviour():
    assert update_clause(("tab_number", "snils")) == "snils = excluded.snils"


def test_with_kept_fills_only_keep_columns():
    before = ("1", "112", None, None, "ОП", "2024-01-10", "2026-08-15", "Переезд", 1, 0)
    row = ("1", "112", None, None, "ОП", "2024-01-10", "2026-08-15", None, None, 0)
    assert with_kept(row, before) == before


def test_with_kept_new_value_wins():
    before = ("1", "112", None, None, "ОП", "2024-01-10", "2026-08-15", "Переезд", 1, 0)
    row = ("1", "112", None, None, "ОП", "2024-01-10", "2026-08-15", "Оплата труда", 1, 0)
    assert with_kept(row, before) == row


def frame(with_reasons: bool) -> pd.DataFrame:
    data = {
        "tab_number": ["1", "2"],
        "snils": ["112-233-445 95", "112-233-445 96"],
        "hire_date": [date(2024, 1, 10), date(2024, 2, 1)],
        "fire_date": [date(2026, 8, 15), None],
    }
    if with_reasons:
        data["fire_reason"] = ["Переезд", None]
        data["counts_in_turnover"] = [True, None]
    return pd.DataFrame(data)


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def stored(conn):
    sql = "SELECT fire_reason, counts_in_turnover FROM episodes WHERE tab_number = '1'"
    return conn.execute(sql).fetchone()


def test_reload_without_reasons_keeps_them(conn):
    upsert_episodes(conn, frame(with_reasons=True))
    stats = upsert_episodes(conn, frame(with_reasons=False))
    assert stored(conn) == ("Переезд", 1)  # не стёрлось
    assert stats == LoadStats(new=0, changed=0, same=2)  # и статистика честная


def test_reload_with_new_reason_updates(conn):
    upsert_episodes(conn, frame(with_reasons=True))
    changed = frame(with_reasons=True)
    changed.loc[0, "fire_reason"] = "Оплата труда"
    stats = upsert_episodes(conn, changed)
    assert stored(conn) == ("Оплата труда", 1)
    assert stats == LoadStats(new=0, changed=1, same=1)
