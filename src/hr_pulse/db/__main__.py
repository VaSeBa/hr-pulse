"""Загрузить выгрузки в базу: uv run python -m hr_pulse.db сотрудники.xlsx причины.xlsx
        [--fire-date "Адрес места проживания"] [--reference справочник.xlsx]
        [--db data/hr_pulse.db] [--on 30.09.2026] [--as-of 31.10.2026] [--force]
Журнал загрузок:  uv run python -m hr_pulse.db --history [--db data/hr_pulse.db]

Склеивает отчёты (шаги 3.2–3.4), загружает эпизоды в базу (новые — добавляет,
известные — обновляет), записывает загрузку в журнал и показывает численность.
Файл старше уже загруженных данных не грузит (если только не --force).
Печатает только числа и имена файлов.
"""

import argparse
from datetime import date
from pathlib import Path

from hr_pulse.core.fields import Field
from hr_pulse.core.formats_1c import parse_ru_date, ru_date
from hr_pulse.db.journal import (
    BackdatedLoadError,
    check_not_backdated,
    format_load,
    latest_event,
    list_loads,
    record_load,
)
from hr_pulse.db.storage import DEFAULT_DB, connect, count_episodes, headcount, upsert_episodes
from hr_pulse.ingest.merge import load_mapped, merge_reasons
from hr_pulse.ingest.reasons import apply_reference, load_reference
from hr_pulse.ingest.rehires import mark_rehires


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить выгрузки в базу данных")
    parser.add_argument("employees", type=Path, nargs="?", help="выгрузка «Личные данные»")
    parser.add_argument("reasons", type=Path, nargs="?", help="выгрузка «Причины увольнений»")
    parser.add_argument("--fire-date", help="колонка с датой увольнения, если не узналась сама")
    parser.add_argument("--reference", type=Path, help="справочник причин «Входит / Не входит»")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="файл базы (%(default)s)")
    parser.add_argument("--on", help="дата для численности, дд.мм.гггг (по умолчанию сегодня)")
    parser.add_argument(
        "--as-of",
        help="на какую дату выгрузка, дд.мм.гггг (по умолчанию — "
        "последняя дата приёма или увольнения в файле)",
    )
    parser.add_argument("--force", action="store_true", help="грузить, даже если файл старше")
    parser.add_argument("--history", action="store_true", help="показать журнал загрузок")
    args = parser.parse_args()

    conn = connect(args.db)
    if args.history:
        loads = list_loads(conn)
        for load in loads:
            print(format_load(load))
        if not loads:
            print("Загрузок ещё не было")
        return
    if args.employees is None or args.reasons is None:
        parser.error("нужны два файла: сотрудники и причины (или ключ --history)")

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

    data_date = parse_ru_date(args.as_of) if args.as_of else latest_event(frame)
    if data_date is None:
        print("В файле нет ни одной даты — укажите дату выгрузки ключом --as-of")
        raise SystemExit(1)
    if not args.force:
        try:
            check_not_backdated(conn, data_date)
        except BackdatedLoadError as error:
            print(f"Загрузка остановлена: {error}")
            print("Если вы уверены (например, исправленная выгрузка), добавьте --force")
            raise SystemExit(1) from error

    stats = upsert_episodes(conn, frame)
    number = record_load(conn, args.employees.name, data_date, stats)

    day = parse_ru_date(args.on) if args.on else date.today()
    print(f"Загрузка №{number}: данные на {ru_date(data_date)}")
    print(f"Новых эпизодов: {stats.new}")
    print(f"Изменилось: {stats.changed}")
    print(f"Без изменений: {stats.same}")
    print(f"Всего в базе: {count_episodes(conn)}")
    print(f"Списочная численность на {ru_date(day)}: {headcount(conn, day)}")
    conn.close()


if __name__ == "__main__":
    main()
