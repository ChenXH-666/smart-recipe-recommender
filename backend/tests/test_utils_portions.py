# -*- coding: utf-8 -*-
"""utils/portions.py —— 用量文本解析工具单元测试。"""
import pytest

from app.utils.portions import parse_grams, split_quantity_units


class TestParseGrams:
    @pytest.mark.parametrize("quantity,expected", [
        ("200克", 200.0),
        ("1千克", 1000.0),
        ("1.5千克", 1500.0),
        ("2公斤", 2000.0),
        ("500g", 500.0),
        ("1斤", 500.0),
        ("2两", 100.0),
    ])
    def test_explicit_weight_units(self, quantity, expected):
        assert parse_grams(quantity) == expected

    @pytest.mark.parametrize("quantity,expected", [
        ("300毫升", 300.0),
        ("200ml", 200.0),
        ("1升", 1000.0),
    ])
    def test_volume_units(self, quantity, expected):
        assert parse_grams(quantity) == expected

    @pytest.mark.parametrize("quantity,expected", [
        ("2碗", 400.0),
        ("1盒", 250.0),
        ("3包", 600.0),
        ("4个", 400.0),   # 可数单位按默认单份 100g
        ("2根", 200.0),
        ("1勺", 15.0),    # 勺子固定 15g
        ("1小勺", 5.0),   # 小勺固定 5g
    ])
    def test_countable_units(self, quantity, expected):
        assert parse_grams(quantity) == expected

    @pytest.mark.parametrize("quantity", ["适量", "少许", "若干"])
    def test_vague_amounts(self, quantity):
        # 模糊表述回归当前语义：视为默认单份
        assert parse_grams(quantity) == 100

    def test_range_takes_average(self):
        # 区间 "100-200克" 取中值 150
        assert parse_grams("100-200克") == 150.0
        assert parse_grams("100~200克") == 150.0

    def test_number_only_multiplies_default(self):
        # 纯数字无单位：按份数 × 默认单份
        assert parse_grams("2") == 200.0
        assert parse_grams("1") == 100.0

    def test_custom_default_per_item(self):
        assert parse_grams("3个", default_per_item=80) == 240.0
        assert parse_grams("适量", default_per_item=50) == 50

    def test_empty_and_none(self):
        assert parse_grams(None) is None
        assert parse_grams("") is None

    def test_no_match_number(self):
        # 无数字且非模糊词 → 默认单份
        assert parse_grams("一把盐") == 100

    def test_spaces_trimmed(self):
        assert parse_grams(" 200 克 ") == 200.0


def test_split_quantity_units_delegates():
    assert split_quantity_units("100克") == parse_grams("100克")