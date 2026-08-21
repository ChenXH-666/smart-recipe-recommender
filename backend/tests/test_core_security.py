# -*- coding: utf-8 -*-
"""core/security.py —— 密码哈希与 JWT 签发/验证单元测试。"""
from datetime import timedelta

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = hash_password("secret123")
        assert h != "secret123"
        assert len(h) > 20

    def test_verify_correct_password(self):
        h = hash_password("secret123")
        assert verify_password("secret123", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("secret123")
        assert verify_password("wrongPass1", h) is False

    def test_salt_makes_hashes_different(self):
        assert hash_password("samePass1") != hash_password("samePass1")

    def test_verify_long_password_truncation_consistent(self):
        # 超 72 字节密码：哈希与校验都截断，验证仍应一致
        long_pwd = "x" * 200 + "9"
        h = hash_password(long_pwd)
        assert verify_password(long_pwd, h) is True


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "42"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "42"

    def test_sub_converted_to_string(self):
        token = create_access_token({"sub": 7})
        assert decode_access_token(token)["sub"] == "7"

    def test_expired_token_returns_none(self):
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-10))
        assert decode_access_token(token) is None

    def test_tampered_token_returns_none(self):
        token = create_access_token({"sub": "1"})
        tampered = token[:-2] + ("ab" if not token.endswith("==") else "00")
        # 篡改签名后应无法通过验签
        assert decode_access_token(tampered) is None

    def test_garbage_token_returns_none(self):
        assert decode_access_token("not-a-jwt") is None