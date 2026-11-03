"""Тесты шага 2.2: превращение колонок выгрузки в даты (hr_pulse.ingest.convert)."""

from datetime import date

import pandas as pd
import pytest

from hr_pulse.demo.export_1c import write_employees_report
from hr_pulse.demo.generator import FakeCompany, GeneratorConfig
from hr_pulse.ingest.convert import date_share, parse_date_columns
from hr_pulse.ingest.reader import read_1c_table

HIRE = "Дата приема"
FIRE = "Адрес места проживания"  # «ловушка»: здесь даты увольнения


@pytest.fixture(scope="module")
def rows():
    return FakeCompany(GeneratorConfig(people=200, seed=3)).generate()


@pytest.fixture(scope="module")
def frame(rows, tmp_path_factory):
    path = tmp_path_factory.mktemp("convert") / "employees.xlsx"
    write_employees_report(rows, path, mislabel_fire_date=True)
    return read_1c_table(path).frame


def test_hire_dates_become_dates(frame, rows):
    parsed = parse_date_columns(frame, [HIRE])
    assert all(isinstance(value, date) for value in parsed[HIRE])
    assert parsed[HIRE].iloc[0] == rows[0].episode.hire_date


def test_empty_fire_date_becomes_none(frame, rows):
    parsed = parse_date_columns(frame, [FIRE])
    for value, row in zip(parsed[FIRE], rows, strict=True):
        assert value == row.episode.fire_date  # дата или None у работающих


def test_original_frame_untouched(frame):
    parse_date_columns(frame, [HIRE])
    assert isinstance(frame[HIRE].iloc[0], str)


def test_trap_column_recognized_as_dates(frame):
    assert date_share(frame[FIRE]) == 1.0
    assert date_share(frame["Должность"]) == 0.0


def test_date_share_of_empty_column():
    assert date_share(pd.Series([None, None], dtype=object)) == 0.0


def test_date_share_partial():
    assert date_share(pd.Series(["10.01.2024", "Монтажник"])) == 0.5
