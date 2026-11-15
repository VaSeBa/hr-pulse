"""Журнал загрузок: что, когда и из какого файла пришло в базу.

Каждая загрузка оставляет строку в таблице loads: когда загрузили, какой файл,
на какую дату данные и сколько эпизодов новых / изменилось / без изменений.
Журнал же защищает от загрузки «задним числом»: сентябрьский файл после
октябрьского откатил бы октябрьские увольнения.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from hr_pulse.core.fields import Field
from hr_pulse.core.formats_1c import is_blank, ru_date
from hr_pulse.db.storage import LoadStats

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS loads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- номер загрузки: 1, 2, 3…
    loaded_at  TEXT NOT NULL,                      -- когда загрузили: «2026-11-15 16:05»
    source     TEXT NOT NULL,                      -- имя файла сотрудников
    data_date  TEXT NOT NULL,                      -- на какую дату данные: «2026-10-31»
    new        INTEGER NOT NULL,
    changed    INTEGER NOT NULL,
    same       INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Load:
    """Одна строка журнала."""

    id: int
    loaded_at: datetime
    source: str
    data_date: date
    new: int
    changed: int
    same: int


class BackdatedLoadError(ValueError):
    """Файл старше того, что уже загружено: загрузка откатила бы свежие данные."""


def latest_event(frame: pd.DataFrame) -> date | None:
    """Самая поздняя дата приёма или увольнения в таблице; дат нет — None."""
    dates = []
    for column in (Field.HIRE_DATE.value, Field.FIRE_DATE.value):
        if column not in frame.columns:
            continue
        for value in frame[column]:
            if not is_blank(value):
                dates.append(value)
    return max(dates) if dates else None


def format_load(load: Load) -> str:
    """Строка журнала для экрана — только числа и имя файла."""
    return (
        f"№{load.id} · {load.loaded_at:%d.%m.%Y %H:%M} · {load.source} · "
        f"данные на {ru_date(load.data_date)} · "
        f"новых {load.new}, изменилось {load.changed}, без изменений {load.same}"
    )


def ensure_journal(conn: sqlite3.Connection) -> None:
    """Создать таблицу журнала, если её ещё нет."""
    conn.executescript(JOURNAL_SCHEMA)


def last_data_date(conn: sqlite3.Connection) -> date | None:
    """На какую дату самые свежие данные в базе; загрузок не было — None."""
    ensure_journal(conn)
    (value,) = conn.execute("SELECT MAX(data_date) FROM loads").fetchone()
    return date.fromisoformat(value) if value else None


def check_not_backdated(conn: sqlite3.Connection, data_date: date) -> None:
    """Остановить загрузку файла, который старше уже загруженных данных."""
    last = last_data_date(conn)
    if last is not None and data_date < last:
        raise BackdatedLoadError(
            f"в базе уже данные на {ru_date(last)}, а файл — на {ru_date(data_date)}. "
            "Загрузка откатит более свежие изменения."
        )


def record_load(
    conn: sqlite3.Connection,
    source: str,
    data_date: date,
    stats: LoadStats,
    now: datetime | None = None,
) -> int:
    """Записать загрузку в журнал. Возвращает её номер."""
    ensure_journal(conn)
    now = now or datetime.now()
    with conn:
        cursor = conn.execute(
            "INSERT INTO loads (loaded_at, source, data_date, new, changed, same) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                now.strftime("%Y-%m-%d %H:%M"),
                source,
                data_date.isoformat(),
                stats.new,
                stats.changed,
                stats.same,
            ),
        )
    return cursor.lastrowid


def list_loads(conn: sqlite3.Connection) -> list[Load]:
    """Весь журнал, от первой загрузки к последней."""
    ensure_journal(conn)
    rows = conn.execute(
        "SELECT id, loaded_at, source, data_date, new, changed, same FROM loads ORDER BY id"
    )
    return [
        Load(
            id=row[0],
            loaded_at=datetime.strptime(row[1], "%Y-%m-%d %H:%M"),
            source=row[2],
            data_date=date.fromisoformat(row[3]),
            new=row[4],
            changed=row[5],
            same=row[6],
        )
        for row in rows
    ]
