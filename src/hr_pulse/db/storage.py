"""База данных SQLite: где хранится история эпизодов между запусками программы.

SQLite — это база в одном файле (data/hr_pulse.db). Сервер не нужен, интернет
не нужен: файл лежит у вас на компьютере. В Git он не попадает (*.db и data/
в .gitignore) — в нём СНИЛС. ФИО в базу не пишем вовсе (минимизация ПДн).
"""

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from hr_pulse.core.formats_1c import is_blank

DEFAULT_DB = Path("data") / "hr_pulse.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    tab_number          TEXT PRIMARY KEY,  -- эпизод: один табельный номер — одна строка
    snils               TEXT NOT NULL,     -- человек
    position            TEXT,
    department          TEXT,
    top_department      TEXT,
    hire_date           TEXT NOT NULL,     -- даты храним текстом «2024-01-10»
    fire_date           TEXT,              -- NULL — работает
    fire_reason         TEXT,
    counts_in_turnover  INTEGER,           -- 1 / 0 / NULL (неизвестно)
    is_technical        INTEGER            -- 1 / 0
);
"""

COLUMNS = (
    "tab_number",
    "snils",
    "position",
    "department",
    "top_department",
    "hire_date",
    "fire_date",
    "fire_reason",
    "counts_in_turnover",
    "is_technical",
)


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Открыть базу (файл создаётся сам, если его нет) и создать таблицы."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)  # папка data/, если её нет
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def to_db_value(value: object) -> object:
    """Значение из таблицы pandas → то, что понимает SQLite.

    Пусто → None (в базе NULL); True/False → 1/0; дата → текст «2024-01-10».
    """
    if is_blank(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, date):
        return date.isoformat(value)
    return value


def episode_rows(frame: pd.DataFrame) -> list[tuple]:
    """Строки таблицы → кортежи значений в порядке COLUMNS. Нет колонки — None."""
    rows = []
    for record in frame.to_dict("records"):  # каждая строка — словарь «колонка → значение»
        rows.append(tuple(to_db_value(record.get(column)) for column in COLUMNS))
    return rows


def save_episodes(conn: sqlite3.Connection, frame: pd.DataFrame) -> int:
    """Записать эпизоды в базу. Возвращает, сколько записано.

    Если такой табельный номер уже есть — sqlite3.IntegrityError
    (повторную загрузку научимся делать в шаге 5.2).
    """
    columns = ", ".join(COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)  # «?, ?, ?…» — места для значений
    rows = episode_rows(frame)
    with conn:  # всё или ничего: при ошибке ни одна строка не запишется
        conn.executemany(f"INSERT INTO episodes ({columns}) VALUES ({marks})", rows)
    return len(rows)


HEADCOUNT_SQL = """
SELECT COUNT(*)
FROM episodes
WHERE hire_date <= :day
    AND (fire_date IS NULL OR fire_date >= :day)
"""


def headcount(conn: sqlite3.Connection, day: date) -> int:
    """Списочная численность на дату: принят не позже дня и не уволен до него."""
    (count,) = conn.execute(HEADCOUNT_SQL, {"day": day.isoformat()}).fetchone()
    return count


def count_episodes(conn: sqlite3.Connection) -> int:
    """Сколько всего эпизодов в базе."""
    (count,) = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
    return count
