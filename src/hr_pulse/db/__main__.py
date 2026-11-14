"""Загрузить выгрузки в базу: uv run python -m hr_pulse.db сотрудники.xlsx причины.xlsx
        [--fire-date "Адрес места проживания"] [--reference справочник.xlsx]
        [--db data/hr_pulse.db] [--on 30.09.2026]

Склеивает отчёты (шаги 3.2–3.4), записывает эпизоды в базу и показывает
численность на дату, посчитанную уже запросом SQL. Печатает только числа.
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path

from hr_pulse.core.fields import Field
from hr_pulse.core.formats_1c import parse_ru_date, ru_date
from hr_pulse.db.storage import DEFAULT_DB, connect, count_episodes, headcount, save_episodes
from hr_pulse.ingest.merge import load_mapped, merge_reasons
from hr_pulse.ingest.reasons import apply_reference, load_reference
from hr_pulse.ingest.rehires import mark_rehires


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить выгрузки в базу данных")
    parser.add_argument("employees", type=Path, help="выгрузка «Личные данные сотрудников»")
    parser.add_argument("reasons", type=Path, help="выгрузка «Причины увольнений»")
    parser.add_argument("--fire-date", help="колонка с датой увольнения, если не узналась сама")
    parser.add_argument("--reference", type=Path, help="справочник причин «Входит / Не входит»")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    parser.add_argument("--on", help="дата для численности, дд.мм.гггг (по умолчанию сегодня)")
    args = parser.parse_args()

    overrides = {args.fire_date: Field.FIRE_DATE} if args.fire_date else None
    try:
        employees = load_mapped(args.employees, overrides)
        frame = merge_reasons(employees, load_mapped(args.reasons)).frame
        if args.reference:
            frame = apply_reference(frame, load_reference(args.reference)).frame
        frame = mark_rehires(frame).frame
    except ValueError as error:
        print(f"Не получилось подготовить данные: {error}")
        raise SystemExit(1) from error

    conn = connect(args.db)
    try:
        saved = save_episodes(conn, frame)
    except sqlite3.IntegrityError as error:
        print("Эти эпизоды уже есть в базе. Повторную загрузку научимся делать в шаге 5.2.")
        print(f"Чтобы начать заново, удалите файл базы: {args.db}")
        raise SystemExit(1) from error

    day = parse_ru_date(args.on) if args.on else date.today()
    print(f"Записано эпизодов: {saved}")
    print(f"Всего в базе: {count_episodes(conn)}")
    print(f"Списочная численность на {ru_date(day)}: {headcount(conn, day)}")
    conn.close()


if __name__ == "__main__":
    main()
