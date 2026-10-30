# -*- coding: utf-8 -*-
"""RAG 写入回归：假 Embedding、内存 Chroma、SQLite 与临时断点文件。"""
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import sessionmaker

import app.services.rag_service as rag
from app.models import Recipe, CookingNote


def _vector(value=1.0):
    return [value] + [0.0] * 1023


@pytest.fixture(autouse=True)
def _isolate_external_services(monkeypatch):
    monkeypatch.setattr(rag, "_kw_index", None)
    monkeypatch.setattr(rag.settings, "EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(rag.settings, "EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setattr(rag.requests, "post", Mock(side_effect=AssertionError("Unexpected HTTP call")))
    monkeypatch.setattr(rag, "get_vectorstore", Mock(side_effect=AssertionError("Unexpected vector store")))


class TestEmbedBatch:
    def _embedding(self, monkeypatch, items, batch_size=64):
        response = Mock()
        response.json.return_value = {"data": items}
        post = Mock(return_value=response)
        monkeypatch.setattr(rag.requests, "post", post)
        monkeypatch.setattr(rag.settings, "RAG_EMBEDDING_BATCH_SIZE", batch_size)
        return rag.SiliconFlowEmbeddings(), post

    def test_splits_requests_and_orders_each_batch(self, monkeypatch):
        emb, post = self._embedding(monkeypatch, [], batch_size=2)
        responses = []
        for values in ((1, 2), (3, 4), (5,)):
            response = Mock()
            response.json.return_value = {"data": [
                {"index": i, "embedding": _vector(value)}
                for i, value in reversed(list(enumerate(values)))
            ]}
            responses.append(response)
        post.side_effect = responses
        assert emb.embed_documents(["a", "b", "c", "d", "e"]) == [
            _vector(i) for i in range(1, 6)
        ]
        assert [c.kwargs["json"]["input"] for c in post.call_args_list] == [
            ["a", "b"], ["c", "d"], ["e"],
        ]
        assert all(c.kwargs["timeout"] == 30 for c in post.call_args_list)

    def test_empty_documents_do_not_request(self, monkeypatch):
        emb, post = self._embedding(monkeypatch, [])
        assert emb.embed_documents([]) == []
        post.assert_not_called()

    @pytest.mark.parametrize("batch_size", [0, -1])
    def test_nonpositive_batch_size_uses_single_request(self, monkeypatch, batch_size):
        items = [{"index": i, "embedding": _vector(i + 1)} for i in range(2)]
        emb, post = self._embedding(monkeypatch, items, batch_size=batch_size)
        assert len(emb.embed_documents(["a", "b"])) == 2
        post.assert_called_once()

    @pytest.mark.parametrize("query", [False, True])
    def test_failure_raises_without_zero_fill(self, monkeypatch, query):
        emb, post = self._embedding(monkeypatch, [], batch_size=1)
        post.side_effect = RuntimeError("embedding down")
        with pytest.raises(RuntimeError, match="embedding down"):
            if query:
                emb.embed_query("红烧肉")
            else:
                emb.embed_documents(["a", "b"])
        assert post.call_count == 1

    def test_later_batch_failure_does_not_return_partial_vectors(self, monkeypatch):
        emb, post = self._embedding(monkeypatch, [{"index": 0, "embedding": _vector()}], 1)
        post.side_effect = [post.return_value, RuntimeError("second batch down")]
        with pytest.raises(RuntimeError, match="second batch"):
            emb.embed_documents(["a", "b", "c"])
        assert post.call_count == 2

    @pytest.mark.parametrize("indices", [
        [0, 0], [-1, 0], [0, 2], [None, 1], ["0", "1"], [False, True], [0.0, 1],
    ])
    def test_invalid_indices_are_rejected(self, monkeypatch, indices):
        emb, _ = self._embedding(monkeypatch, [
            {"index": index, "embedding": _vector()} for index in indices
        ])
        with pytest.raises(ValueError, match="索引"):
            emb.embed_documents(["a", "b"])

    def test_missing_index_is_rejected(self, monkeypatch):
        emb, _ = self._embedding(monkeypatch, [{"embedding": _vector()}])
        with pytest.raises(ValueError, match="索引"):
            emb.embed_query("a")

    @pytest.mark.parametrize("count", [0, 1, 3])
    def test_response_count_must_match(self, monkeypatch, count):
        emb, _ = self._embedding(monkeypatch, [
            {"index": i, "embedding": _vector()} for i in range(count)
        ])
        with pytest.raises(ValueError, match="条数"):
            emb.embed_documents(["a", "b"])

    @pytest.mark.parametrize("vector", [
        None, [], [1.0], [0.0] * 1024, _vector(float("nan")),
        _vector(float("inf")), _vector("1"), _vector(True),
    ], ids=["missing", "empty", "dimension", "zero", "nan", "inf", "string", "bool"])
    def test_malformed_vectors_are_rejected(self, monkeypatch, vector):
        emb, _ = self._embedding(monkeypatch, [{"index": 0, "embedding": vector}])
        with pytest.raises(ValueError):
            emb.embed_query("a")

    def test_other_model_requires_consistent_dimensions_across_batches(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "EMBEDDING_MODEL", "other-model")
        emb, post = self._embedding(monkeypatch, [{"index": 0, "embedding": [1.0, 2.0]}], 1)
        second = Mock()
        second.json.return_value = {"data": [{"index": 0, "embedding": [1.0]}]}
        post.side_effect = [post.return_value, second]
        with pytest.raises(ValueError, match="维度"):
            emb.embed_documents(["a", "b"])


class _Embedding:
    def __init__(self):
        self.calls = []
        self.fail_on = None

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        if len(self.calls) == self.fail_on:
            raise RuntimeError("embedding unavailable")
        return [_vector() for _ in texts]


@pytest.fixture()
def store(monkeypatch, tmp_path):
    client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
    name = "rag-test-" + uuid4().hex
    embedding = _Embedding()
    vs = rag.Chroma(client=client, collection_name=name, embedding_function=embedding)
    collection = Mock(wraps=vs._collection)
    monkeypatch.setattr(vs, "_collection", collection)
    monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
    monkeypatch.setattr(rag, "_get_embedding_model", lambda: embedding)
    monkeypatch.setattr(rag.settings, "RAG_EMBEDDING_BATCH_SIZE", 1)
    checkpoint = tmp_path / "checkpoint.json"
    monkeypatch.setattr(rag, "_get_checkpoint_path", lambda: str(checkpoint))
    yield SimpleNamespace(vs=vs, collection=collection, embedding=embedding, checkpoint=checkpoint)
    client.delete_collection(name)


def _seed(store, ids, source_type="recipe", source_id=7):
    store.collection.upsert(
        ids=ids, embeddings=[_vector(9) for _ in ids],
        documents=["old:" + doc_id for doc_id in ids],
        metadatas=[{"source_type": source_type, "source_id": source_id} for _ in ids],
    )
    store.collection.reset_mock()


def _documents(store):
    result = store.collection.get(include=["documents"])
    return dict(zip(result["ids"], result["documents"]))


def _source(kind):
    if kind == "recipe":
        return SimpleNamespace(id=7, title="红烧肉", description="家常菜", estimated_cost=20,
                               tags=[], ingredients=[], steps=[]), rag.sync_recipe_to_chroma, "recipe"
    return SimpleNamespace(id=7, title="火候", content="小火慢炖"), rag.sync_cooking_note_to_chroma, "note"


class TestSyncSource:
    @pytest.mark.parametrize("kind", ["recipe", "cooking_note"])
    def test_upsert_before_removing_stale_chunks(self, store, kind, monkeypatch):
        source, sync, prefix = _source(kind)
        old_ids = [f"{prefix}_7_0", f"{prefix}_7_1"]
        _seed(store, old_ids, kind)
        _seed(store, ["unrelated"], kind, source_id=8)
        monkeypatch.setattr(rag, "_kw_index", {"stale": True})
        sync(source)
        docs = _documents(store)
        assert set(docs) == {old_ids[0], "unrelated"}
        assert source.title in docs[old_ids[0]]
        operations = [call[0] for call in store.collection.mock_calls]
        assert operations.index("upsert") < operations.index("delete")
        store.collection.delete.assert_called_once_with(ids=[old_ids[1]])
        assert rag._kw_index is None

    @pytest.mark.parametrize("kind", ["recipe", "cooking_note"])
    @pytest.mark.parametrize("failure", ["embedding", "upsert"])
    def test_failed_write_preserves_existing_chunks(self, store, kind, failure):
        source, sync, prefix = _source(kind)
        _seed(store, [f"{prefix}_7_0", f"{prefix}_7_1"], kind)
        before = _documents(store)
        if failure == "embedding":
            store.embedding.fail_on = 1
        else:
            store.collection.upsert.side_effect = RuntimeError("storage unavailable")
        with pytest.raises(RuntimeError):
            sync(source)
        assert _documents(store) == before
        store.collection.delete.assert_not_called()

    def test_cleanup_failure_is_reported_and_retryable(self, store):
        source, sync, _ = _source("recipe")
        _seed(store, ["recipe_7_0", "recipe_7_1"])
        store.collection.delete.side_effect = RuntimeError("delete failed")
        with pytest.raises(RuntimeError, match="delete failed"):
            sync(source)
        assert set(_documents(store)) == {"recipe_7_0", "recipe_7_1"}
        store.collection.delete.side_effect = None
        sync(source)
        assert set(_documents(store)) == {"recipe_7_0"}

    def test_remove_uses_valid_compound_filter_and_keeps_other_sources(self, store):
        _seed(store, ["recipe_7_0", "recipe_7_1"])
        _seed(store, ["recipe_8_0"], source_id=8)
        _seed(store, ["note_7_0"], "cooking_note")
        rag.remove_from_chroma("recipe", 7)
        assert set(_documents(store)) == {"recipe_8_0", "note_7_0"}
        store.collection.delete.assert_called_once_with(where={"$and": [
            {"source_type": "recipe"}, {"source_id": 7},
        ]})

    def test_remove_failure_does_not_log_success(self, store, caplog):
        _seed(store, ["recipe_7_0"])
        store.collection.delete.side_effect = RuntimeError("delete unavailable")
        with caplog.at_level("INFO", logger=rag.__name__):
            with pytest.raises(RuntimeError):
                rag.remove_from_chroma("recipe", 7)
        assert "已从向量库移除" not in caplog.text
        assert "old:recipe_7_0" == _documents(store)["recipe_7_0"]


class TestSyncById:
    @pytest.mark.parametrize("status,deleted,action", [
        ("pending", 0, "remove"), ("approved", 1, "skip"), ("approved", 0, "sync"),
    ])
    def test_recipe_visibility(self, db, engine, monkeypatch, status, deleted, action):
        recipe = Recipe(title="测试菜", status=status, is_deleted=deleted)
        db.add(recipe)
        db.commit()
        monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=engine))
        remove, sync = Mock(), Mock()
        monkeypatch.setattr(rag, "remove_from_chroma", remove)
        monkeypatch.setattr(rag, "sync_recipe_to_chroma", sync)
        rag.sync_recipe_to_chroma_by_id(recipe.id)
        assert remove.call_count == (action == "remove")
        assert sync.call_count == (action == "sync")
        if action == "remove":
            remove.assert_called_once_with("recipe", recipe.id)


class TestRebuildVectorstore:
    def test_rebuild_indexes_visible_content_then_removes_obsolete_chunks(self, db, store):
        approved = Recipe(title="红烧肉", status="approved")
        pending = Recipe(title="待审核菜", status="pending")
        deleted = Recipe(title="已删除菜", status="approved", is_deleted=1)
        public = CookingNote(user_id=1, title="公开心得", content="火候", is_public=1)
        private = CookingNote(user_id=1, title="私密心得", content="私密", is_public=0)
        removed = CookingNote(user_id=1, title="删除心得", content="删除", is_deleted=1)
        db.add_all([approved, pending, deleted, public, private, removed])
        db.commit()
        _seed(store, ["obsolete"])
        rag.rebuild_vectorstore(db, resume=False)
        assert set(_documents(store)) == {f"recipe_{approved.id}_0", f"note_{public.id}_0"}
        operations = [call[0] for call in store.collection.mock_calls]
        assert operations.index("delete") > max(i for i, name in enumerate(operations) if name == "upsert")
        assert not store.checkpoint.exists()

    @pytest.mark.parametrize("failure", ["embedding", "upsert"])
    def test_failure_preserves_unwritten_batch_and_checkpoint_then_resumes(self, db, store, failure):
        db.add_all([Recipe(id=1, title="甲菜", status="approved"),
                    Recipe(id=2, title="乙菜", status="approved")])
        db.commit()
        _seed(store, ["recipe_1_0", "recipe_2_0", "obsolete"])
        if failure == "embedding":
            store.embedding.fail_on = 2
        else:
            original = store.collection.upsert._mock_wraps
            calls = []
            def fail_second(**kwargs):
                calls.append(kwargs)
                if len(calls) == 2:
                    raise RuntimeError("upsert failed")
                return original(**kwargs)
            store.collection.upsert.side_effect = fail_second
        with pytest.raises(RuntimeError):
            rag.rebuild_vectorstore(db, resume=False)
        docs = _documents(store)
        assert "甲菜" in docs["recipe_1_0"]
        assert docs["recipe_2_0"] == "old:recipe_2_0"
        assert "obsolete" in docs
        assert json.loads(store.checkpoint.read_text())["done_ids"] == ["recipe_1_0"]
        store.collection.delete.assert_not_called()

        store.embedding.fail_on = None
        store.embedding.calls.clear()
        store.collection.upsert.side_effect = None
        rag.rebuild_vectorstore(db, resume=True)
        assert set(_documents(store)) == {"recipe_1_0", "recipe_2_0"}
        assert len(store.embedding.calls) == 1
        assert "乙菜" in store.embedding.calls[0][0]
        assert not store.checkpoint.exists()

    def test_cleanup_failure_preserves_checkpoint_and_resume_finishes_cleanup(self, db, store):
        db.add(Recipe(id=1, title="正常菜", status="approved"))
        db.commit()
        _seed(store, ["obsolete"])
        store.collection.delete.side_effect = RuntimeError("delete failed")
        with pytest.raises(RuntimeError):
            rag.rebuild_vectorstore(db, resume=False)
        assert json.loads(store.checkpoint.read_text())["done_ids"] == ["recipe_1_0"]
        store.collection.delete.side_effect = None
        store.embedding.calls.clear()
        rag.rebuild_vectorstore(db, resume=True)
        assert store.embedding.calls == []
        assert set(_documents(store)) == {"recipe_1_0"}
        assert not store.checkpoint.exists()

    def test_missing_checkpointed_vector_is_reencoded(self, db, store):
        db.add(Recipe(id=1, title="正常菜", status="approved"))
        db.commit()
        store.checkpoint.write_text(json.dumps({"done_ids": ["recipe_1_0"]}))
        rag.rebuild_vectorstore(db, resume=True)
        assert set(_documents(store)) == {"recipe_1_0"}
        assert len(store.embedding.calls) == 1

    @pytest.mark.parametrize("resume", [False, True])
    def test_empty_source_still_removes_obsolete_chunks(self, db, store, resume, monkeypatch):
        _seed(store, ["obsolete"])
        monkeypatch.setattr(rag.settings, "RAG_EMBEDDING_BATCH_SIZE", 0)
        rag.rebuild_vectorstore(db, resume=resume)
        assert _documents(store) == {}
        assert store.embedding.calls == []
        assert not store.checkpoint.exists()

    def test_checkpoint_replace_failure_keeps_previous_progress(self, db, store, monkeypatch):
        db.add_all([Recipe(id=1, title="甲菜", status="approved"),
                    Recipe(id=2, title="乙菜", status="approved")])
        db.commit()
        _seed(store, ["recipe_1_0", "obsolete"])
        store.checkpoint.write_text(json.dumps({"done_ids": ["recipe_1_0"]}))
        monkeypatch.setattr(rag.os, "replace", Mock(side_effect=OSError("disk full")))
        with pytest.raises(OSError, match="disk full"):
            rag.rebuild_vectorstore(db, resume=True)
        assert json.loads(store.checkpoint.read_text())["done_ids"] == ["recipe_1_0"]
        store.collection.delete.assert_not_called()


class TestFallbackMetadataSearch:
    def test_orders_by_keyword_score(self):
        docs = [
            ("菜谱：清炒时蔬", {"source_type": "recipe", "source_id": 1, "title": "清炒时蔬", "tags": "素菜"}),
            ("菜谱：红烧排骨", {"source_type": "recipe", "source_id": 2, "title": "红烧排骨", "tags": "下饭"}),
            ("菜谱：红烧茄子", {"source_type": "recipe", "source_id": 3, "title": "红烧茄子", "tags": "家常"}),
        ]
        vs = SimpleNamespace(_collection=SimpleNamespace(get=lambda **kwargs: {
            "documents": [d for d, _ in docs], "metadatas": [m for _, m in docs],
        }))
        res = rag._fallback_metadata_search(vs, "红烧排骨", 5, "recipe")
        assert [r["source_id"] for r in res] == [2, 3]

    def test_no_token_match_returns_empty(self):
        vs = SimpleNamespace(_collection=SimpleNamespace(get=lambda **kwargs: {
            "documents": ["菜谱：清炒时蔬"],
            "metadatas": [{"source_type": "recipe", "source_id": 1, "title": "清炒时蔬", "tags": ""}],
        }))
        assert rag._fallback_metadata_search(vs, "披萨", 5, "recipe") == []
