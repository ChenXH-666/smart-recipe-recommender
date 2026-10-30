# -*- coding: utf-8 -*-
"""AI 对话 SSE 接口测试 —— 流式输出、消息持久化、失败降级、会话权限。

关键隔离：
  - conftest.client 只覆盖 get_db；api/ai.py 保存 AI 回复时用的是模块级
    SessionLocal（生产 MySQL），因此这里必须把它换成 SQLite 测试会话工厂。
  - chat_stream 整体打桩为可控异步生成器，绝不触达 LLM / Embedding / Chroma。
"""
import asyncio
import json
from collections import OrderedDict
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import AiConversation, AiMessage, User
from app.schemas.ai import AiChatRequest
from app.services import ai_service
from app.services.ai_service import AI_ERROR_MSG


def _register(client, username="chef", email="chef@a.com", password="pass1234"):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _login(client, username="chef", password="pass1234"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _stream_of(chunks, exc=None):
    """构造 fake chat_stream：逐条 yield，最后可选抛异常。"""
    async def _gen(*args, **kwargs):
        for chunk in chunks:
            yield chunk
        if exc is not None:
            raise exc
    return _gen


def _parse_sse(body):
    assert body.endswith("\n\n")
    frames = []
    for frame in body[:-2].split("\n\n"):
        assert frame.startswith("data: ")
        assert "\n" not in frame
        payload = frame[len("data: "):]
        frames.append(payload if payload == "[DONE]" else json.loads(payload))
    return frames


@pytest.fixture(autouse=True)
def isolated_memories(monkeypatch):
    memories = OrderedDict()
    monkeypatch.setattr(ai_service, "_conversation_memories", memories)
    return memories


@pytest.fixture()
def sse_user(db):
    user = User(username="owner", email="owner@example.com", password_hash="unused")
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def patch_sse_session(db_engine, monkeypatch):
    """把 app.api.ai.SessionLocal 指向 SQLite 测试库，避免写真实 MySQL。"""
    import app.api.ai as ai_api

    Session = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(ai_api, "SessionLocal", Session)
    return ai_api


def _messages(db, conversation_id):
    db.expire_all()
    return (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.id.asc())
        .all()
    )


class TestAiChatSse:
    def test_stream_persists_user_and_assistant_messages(
        self, client, db, patch_sse_session, monkeypatch
    ):
        _register(client)
        token = _login(client)
        chunks = ['你好\n"大厨"', '\n\n先放盐，再加"水"。']
        monkeypatch.setattr(patch_sse_session, "chat_stream", _stream_of(chunks))

        r = client.post("/api/ai/chat", json={"message": "推荐两道菜"},
                        headers=_auth(token))

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "X-Conversation-Id" in r.headers
        assert _parse_sse(r.text) == [*chunks, "[DONE]"]

        cid = int(r.headers["X-Conversation-Id"])
        msgs = _messages(db, cid)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[0].content == "推荐两道菜"
        assert msgs[1].content == "".join(chunks)

    @pytest.mark.parametrize("chunks", [[], ['部分\n"正文"']])
    def test_stream_exception_yields_error_and_done_without_persisting(
        self, client, db, patch_sse_session, monkeypatch, chunks
    ):
        _register(client)
        token = _login(client)
        monkeypatch.setattr(patch_sse_session, "chat_stream",
                            _stream_of(chunks, RuntimeError("private llm failure")))
        factory = Mock(side_effect=AssertionError("must not persist"))
        monkeypatch.setattr(patch_sse_session, "SessionLocal", factory)

        r = client.post("/api/ai/chat", json={"message": "推荐两道菜"},
                        headers=_auth(token))

        assert r.status_code == 200
        assert _parse_sse(r.text) == [*chunks, AI_ERROR_MSG, "[DONE]"]
        factory.assert_not_called()

        cid = int(r.headers["X-Conversation-Id"])
        assert [m.role for m in _messages(db, cid)] == ["user"]

    def test_partial_body_saved_without_error_suffix(
        self, client, db, patch_sse_session, monkeypatch
    ):
        _register(client)
        token = _login(client)
        chunks = ["部分正文", AI_ERROR_MSG]
        monkeypatch.setattr(patch_sse_session, "chat_stream", _stream_of(chunks))

        r = client.post("/api/ai/chat", json={"message": "推荐两道菜"},
                        headers=_auth(token))

        assert r.status_code == 200
        assert _parse_sse(r.text) == [*chunks, "[DONE]"]
        cid = int(r.headers["X-Conversation-Id"])
        msgs = _messages(db, cid)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[1].content == "部分正文"

    @pytest.mark.parametrize("chunks", [[AI_ERROR_MSG], [" \n", AI_ERROR_MSG]])
    def test_only_error_message_is_not_persisted(
        self, client, db, patch_sse_session, monkeypatch, chunks
    ):
        _register(client)
        token = _login(client)
        monkeypatch.setattr(patch_sse_session, "chat_stream", _stream_of(chunks))
        factory = Mock(side_effect=AssertionError("must not persist"))
        monkeypatch.setattr(patch_sse_session, "SessionLocal", factory)

        r = client.post("/api/ai/chat", json={"message": "推荐两道菜"},
                        headers=_auth(token))

        assert r.status_code == 200
        assert _parse_sse(r.text) == [*chunks, "[DONE]"]
        factory.assert_not_called()
        cid = int(r.headers["X-Conversation-Id"])
        assert [m.role for m in _messages(db, cid)] == ["user"]

    @pytest.mark.parametrize(("chunks", "saved_text"), [
        (['完整\n"回复"', "。"], '完整\n"回复"。'),
        (["部分正文", AI_ERROR_MSG], "部分正文"),
        (["部分正文" + AI_ERROR_MSG], "部分正文"),
        ([], "（AI 未返回有效内容）"),
        (["", " \n"], "（AI 未返回有效内容）"),
    ])
    def test_assistant_is_committed_at_done(
        self, db, db_engine, sse_user, patch_sse_session, monkeypatch, chunks, saved_text
    ):
        monkeypatch.setattr(patch_sse_session, "chat_stream", _stream_of(chunks))
        verify_session = sessionmaker(bind=db_engine)

        async def consume():
            response = await patch_sse_session.ai_chat(
                AiChatRequest(message="推荐两道菜"), db=db, current_user=sse_user,
            )
            cid = int(response.headers["X-Conversation-Id"])
            frames = []
            # TestClient 会耗尽响应，必须在收到 DONE 的当下检查数据库。
            async for frame in response.body_iterator:
                frames.extend(_parse_sse(frame))
                if frame == "data: [DONE]\n\n":
                    with verify_session() as persisted_db:
                        messages = _messages(persisted_db, cid)
                        assert [m.role for m in messages] == ["user", "assistant"]
                        assert messages[1].content == saved_text
            assert frames == [*chunks, "[DONE]"]

        asyncio.run(consume())

    @pytest.mark.parametrize("failure", ["factory", "commit", "rollback", "close"])
    def test_save_failure_warns_invalidates_memory_and_finishes(
        self, db, sse_user, patch_sse_session, monkeypatch, caplog, failure
    ):
        reply = '生成的\n"回复"'
        detail = "mysql://test_user:private-password@db.invalid/recipes"
        memory_seen = []

        async def stream_with_memory(message, conversation_id, **kwargs):
            memory = ai_service._conversation_memories[conversation_id]
            memory.save_context({"input": message}, {"output": reply})
            memory_seen.append(conversation_id)
            yield reply

        monkeypatch.setattr(patch_sse_session, "chat_stream", stream_with_memory)
        sse_db = None
        if failure == "factory":
            factory = Mock(side_effect=RuntimeError(detail))
        else:
            real_session = patch_sse_session.SessionLocal()
            sse_db = Mock(wraps=real_session)
            sse_db.commit.side_effect = RuntimeError(detail)
            if failure == "rollback":
                sse_db.rollback.side_effect = RuntimeError("rollback failed")
            if failure == "close":
                def close_then_fail():
                    real_session.close()
                    raise RuntimeError("close failed")

                sse_db.close.side_effect = close_then_fail
            factory = Mock(return_value=sse_db)
        monkeypatch.setattr(patch_sse_session, "SessionLocal", factory)

        async def consume():
            response = await patch_sse_session.ai_chat(
                AiChatRequest(message="推荐两道菜"), db=db, current_user=sse_user,
            )
            cid = int(response.headers["X-Conversation-Id"])
            frames = []
            async for frame in response.body_iterator:
                frames.extend(_parse_sse(frame))
                if frame == "data: [DONE]\n\n":
                    assert memory_seen == [cid]
                    assert not ai_service.has_memory(cid)
                    factory.assert_called_once_with()
                    if sse_db is not None:
                        sse_db.commit.assert_called_once_with()
                        sse_db.rollback.assert_called_once_with()
                        sse_db.close.assert_called_once_with()
                    assert [m.role for m in _messages(db, cid)] == ["user"]
            assert frames == [reply, "回答已生成，但保存失败，请稍后重试。", "[DONE]"]

        asyncio.run(consume())
        assert detail in caplog.text

    @pytest.mark.parametrize("other_user", [False, True])
    def test_unknown_or_other_user_conversation_returns_404(
        self, client, db, sse_user, patch_sse_session, monkeypatch, other_user,
        isolated_memories,
    ):
        _register(client)
        token = _login(client)
        conv = AiConversation(user_id=sse_user.id, title="private conversation")
        db.add(conv)
        db.commit()
        stream = Mock(side_effect=AssertionError("must not generate"))
        monkeypatch.setattr(patch_sse_session, "chat_stream", stream)

        r = client.post("/api/ai/chat",
                        json={"message": "继续聊", "conversation_id": conv.id if other_user else 999999},
                        headers=_auth(token))
        assert r.status_code == 404
        assert r.json() == {"code": 404, "message": "会话不存在", "detail": None}
        assert db.query(AiMessage).count() == 0
        assert db.query(AiConversation).count() == 1
        assert not isolated_memories
        stream.assert_not_called()

    def test_requires_login(self, client, patch_sse_session):
        r = client.post("/api/ai/chat", json={"message": "推荐两道菜"})
        assert r.status_code == 401
