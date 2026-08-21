# -*- coding: utf-8 -*-
"""utils/validation.py —— 封面图白名单、URL 清洗、整型列表解析单元测试。"""
import pytest

from app.utils.validation import (
    is_safe_recipe_cover_url,
    sanitize_recipe_cover,
    parse_int_list,
)


class TestIsSafeRecipeCoverUrl:
    def test_none_or_empty_allowed(self):
        assert is_safe_recipe_cover_url(None) is True
        assert is_safe_recipe_cover_url("") is True

    def test_local_static_path_allowed(self):
        assert is_safe_recipe_cover_url("/static/recipe_covers/recipe_1.jpg") is True

    def test_https_whitelist_domain_allowed(self):
        assert is_safe_recipe_cover_url("https://www.meishichina.com/a.jpg") is True

    def test_subdomain_allowed(self):
        assert is_safe_recipe_cover_url("https://i.xiachufang.com/a.jpg") is True

    def test_http_rejected(self):
        assert is_safe_recipe_cover_url("http://www.meishichina.com/a.jpg") is False

    def test_non_whitelist_rejected(self):
        assert is_safe_recipe_cover_url("https://example.com/a.jpg") is False

    def test_double_slash_rejected(self):
        assert is_safe_recipe_cover_url("//evil.com/a.jpg") is False

    def test_no_scheme_rejected(self):
        assert is_safe_recipe_cover_url("meishichina.com/a.jpg") is False


class TestSanitizeRecipeCover:
    def test_safe_url_returned(self):
        assert sanitize_recipe_cover("https://www.meishichina.com/a.jpg") == "https://www.meishichina.com/a.jpg"

    def test_unsafe_falls_back_to_default(self):
        assert sanitize_recipe_cover("https://example.com/a.jpg") == "/static/recipe_covers/default.jpg"

    def test_empty_falls_back(self):
        assert sanitize_recipe_cover("") == "/static/recipe_covers/default.jpg"

    def test_example_com_placeholder_rejected(self):
        assert sanitize_recipe_cover("https://example.com/foo") == "/static/recipe_covers/default.jpg"


class TestParseIntList:
    def test_basic(self):
        assert parse_int_list("1,2,3") == [1, 2, 3]

    def test_skips_invalid_parts(self):
        assert parse_int_list("1,a,3") == [1, 3]

    def test_none_or_empty(self):
        assert parse_int_list(None) == []
        assert parse_int_list("") == []

    def test_whitespace_handled(self):
        assert parse_int_list(" 1 , 2 ") == [1, 2]

    def test_max_items_truncation(self):
        assert parse_int_list("1,2,3,4", max_items=2) == [1, 2]

    def test_negative_numbers(self):
        assert parse_int_list("1,-2,3") == [1, -2, 3]