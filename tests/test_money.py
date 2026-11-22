"""Тесты шага 7.1: параметры и стоимость текучести."""

import json

import pytest

from hr_pulse.money.cost import (
    RAMP_UP,
    cost_breakdown,
    cost_by_department,
    rub,
    total,
)
from hr_pulse.money.params import (
    DEFAULTS,
    changed_keys,
    describe_params,
    format_value,
    load_params,
    merge_params,
    parse_amount,
    save_params,
)

# ---------- пример к задаче 1 ----------


def test_changed_keys():
    assert changed_keys(DEFAULTS) == []
    assert changed_keys({**DEFAULTS, "проезд": 30000, "зарплата": 100000}) == ["проезд", "зарплата"]


# ---------- Задача 1: merge_params ----------


def test_merge_params_empty_gives_defaults():
    params, unknown = merge_params({})
    assert params == DEFAULTS
    assert unknown == []


def test_merge_params_replaces_known():
    params, unknown = merge_params({"проезд": 30000})
    assert params["проезд"] == 30000
    assert params["подбор"] == DEFAULTS["подбор"]  # остальные — по умолчанию
    assert unknown == []


def test_merge_params_skips_unknown():
    params, unknown = merge_params({"прозд": 1, "проезд": 30000, "премия": 5})
    assert "прозд" not in params
    assert params["проезд"] == 30000
    assert unknown == ["прозд", "премия"]


def test_merge_params_does_not_change_defaults():
    merge_params({"проезд": 1})
    assert DEFAULTS["проезд"] == 25_000  # копия, а не сами значения по умолчанию


def test_merge_params_makes_float():
    params, _ = merge_params({"адаптация_мес": "2"})
    assert params["адаптация_мес"] == 2.0


# ---------- Задача 2: cost_breakdown ----------


def test_cost_breakdown_defaults():
    rows = cost_breakdown(DEFAULTS)
    assert rows[0] == ("Подбор", 15_000)
    assert rows[-1] == (RAMP_UP, pytest.approx(90_000))  # 120 000 × 1,5 × 50 %
    assert len(rows) == 7


def test_cost_breakdown_total_defaults():
    assert total(cost_breakdown(DEFAULTS)) == pytest.approx(168_000)


def test_cost_breakdown_no_adaptation():
    params = {**DEFAULTS, "потеря_выработки": 0}
    assert cost_breakdown(params)[-1] == (RAMP_UP, 0)


def test_cost_breakdown_uses_params():
    params = {**DEFAULTS, "проезд": 40_000, "зарплата": 100_000, "адаптация_мес": 2}
    rows = dict(cost_breakdown(params))
    assert rows["Проезд на первую вахту"] == 40_000
    assert rows[RAMP_UP] == pytest.approx(100_000)  # 100 000 × 2 × 50 %


# ---------- готовые помощники ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("30000", 30000, id="plain"),
        pytest.param("30 000 ₽", 30000, id="spaces-rub"),
        pytest.param("1,5", 1.5, id="comma"),
        pytest.param("50 %", 50, id="percent"),
        pytest.param("0", 0, id="zero"),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("", "не указано", id="empty"),
        pytest.param("много", "не число", id="text"),
        pytest.param("-5", "меньше нуля", id="negative"),
    ],
)
def test_parse_amount_bad(text, message):
    with pytest.raises(ValueError, match=message):
        parse_amount(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(15000, "15 000", id="thousands"),
        pytest.param(1.5, "1,5", id="fraction"),
        pytest.param(50.0, "50", id="whole-float"),
    ],
)
def test_format_value(value, expected):
    assert format_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(10_920_000, "10 920 000 ₽", id="millions"),
        pytest.param(90_000.4, "90 000 ₽", id="rounded"),
        pytest.param(0, "0 ₽", id="zero"),
    ],
)
def test_rub(value, expected):
    assert rub(value) == expected


def test_describe_params_all_keys():
    lines = describe_params(DEFAULTS)
    assert len(lines) == len(DEFAULTS)
    assert lines[4] == "проезд — 25 000 (Проезд на первую вахту, ₽)"


def test_cost_by_department():
    rows = cost_by_department([("ОП Северное", 33), ("ОП Центральное", 2)], 168_000)
    assert rows == [("ОП Северное", 33, 5_544_000), ("ОП Центральное", 2, 336_000)]


# ---------- файл параметров ----------


def test_load_params_no_file(tmp_path):
    assert load_params(tmp_path / "нет.json") == (DEFAULTS, [])


def test_save_and_load(tmp_path):
    path = tmp_path / "data" / "cost_params.json"
    save_params({**DEFAULTS, "проезд": 30000.0}, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["проезд"] == 30000  # целое без «.0»
    assert "проезд" in path.read_text(encoding="utf-8")  # по-русски, а не \\u043f…
    params, unknown = load_params(path)
    assert params["проезд"] == 30000
    assert unknown == []


def test_load_params_broken_file(tmp_path):
    path = tmp_path / "cost_params.json"
    path.write_text('{"проезд": 30000,', encoding="utf-8")
    with pytest.raises(ValueError, match="испорчен"):
        load_params(path)


def test_load_params_not_dict(tmp_path):
    path = tmp_path / "cost_params.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="словарь"):
        load_params(path)
