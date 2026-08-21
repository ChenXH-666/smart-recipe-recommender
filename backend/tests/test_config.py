# -*- coding: utf-8 -*-
"""config.py —— 配置属性与安全自检单元测试。

说明：通过显式传入参数构造 Settings，避免受 .env 影响，保证测试确定性。
"""
from app.config import Settings


def _settings(**overrides):
    base = dict(
        DB_HOST="localhost", DB_PORT=3306, DB_USER="root",
        DB_PASSWORD="123", DB_NAME="recipe_system", DB_CHARSET="utf8mb4",
        JWT_SECRET_KEY="a-strong-test-secret-at-least-32-chars-long!!",
        CORS_ALLOW_ORIGINS="*",
        RECIPE_COVER_WHITELIST="meishichina.com,xiachufang.com",
    )
    base.update(overrides)
    return Settings(**base)


class TestDatabaseUrl:
    def test_components_joined(self):
        s = _settings(
            DB_HOST="db.local", DB_PORT=3307, DB_USER="app",
            DB_PASSWORD="secret", DB_NAME="recipe",
        )
        url = s.DATABASE_URL
        assert url.startswith("mysql+pymysql://")
        assert "app:secret@db.local:3307/recipe" in url
        assert "charset=utf8mb4" in url

    def test_default_password_url(self):
        s = _settings()
        assert "root:123@localhost:3306/recipe_system" in s.DATABASE_URL


class TestJwtSecretStrength:
    def test_weak_placeholder_detected(self):
        assert _settings(JWT_SECRET_KEY="CHANGE-ME-IN-PRODUCTION-USE-STRONG-RANDOM-SECRET").is_jwt_secret_weak is True

    def test_short_secret_detected(self):
        assert _settings(JWT_SECRET_KEY="short").is_jwt_secret_weak is True

    def test_strong_secret_ok(self):
        assert _settings(JWT_SECRET_KEY="A" * 40).is_jwt_secret_weak is False


class TestCorsParsing:
    def test_wildcard(self):
        assert _settings(CORS_ALLOW_ORIGINS="*").cors_allow_origins_list == ["*"]

    def test_empty(self):
        assert _settings(CORS_ALLOW_ORIGINS="").cors_allow_origins_list == ["*"]

    def test_comma_list(self):
        assert _settings(CORS_ALLOW_ORIGINS="https://a.com, https://b.com").cors_allow_origins_list == [
            "https://a.com", "https://b.com",
        ]


class TestCoverWhitelist:
    def test_separated(self):
        assert _settings().recipe_cover_whitelist_list == [
            "meishichina.com", "xiachufang.com",
        ]