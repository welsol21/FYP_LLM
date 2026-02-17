import unittest
from unittest.mock import patch

from ela_pipeline.db.persistence import persist_inference_result


class _FakeCursor:
    def __init__(self):
        self.calls = []
        self.fetchone_queue = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        if self.fetchone_queue:
            return self.fetchone_queue.pop(0)
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commit_count += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DBPersistenceTests(unittest.TestCase):
    def test_persist_requires_db_url(self):
        with patch.dict("os.environ", {"ELA_DATABASE_URL": "", "DATABASE_URL": ""}, clear=False):
            with self.assertRaises(ValueError):
                persist_inference_result(
                    result={},
                    db_url="",
                    source_lang="en",
                    target_lang="none",
                    pipeline_context={},
                )

    def test_persist_inference_result_upserts_run_and_sentence(self):
        connections = []

        def connect_fn(_db_url):
            conn = _FakeConnection()
            connections.append(conn)
            return conn

        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "tam_construction": "simple_past",
                "backoff_nodes_count": 1,
                "backoff_leaf_nodes_count": 1,
                "backoff_aggregate_nodes_count": 0,
                "backoff_unique_spans_count": 1,
                "linguistic_elements": [],
            }
        }

        mapping = persist_inference_result(
            result=result,
            db_url="postgresql://local/test",
            source_lang="en",
            target_lang="ru",
            pipeline_context={"cefr_provider": "t5"},
            run_id="run-1",
            connect_fn=connect_fn,
        )

        self.assertIn("She trusted him.", mapping)
        self.assertEqual(len(mapping["She trusted him."]), 64)

        executed = [call for conn in connections for call in conn.cursor_obj.calls]
        self.assertGreaterEqual(len(executed), 3)  # schema + run + sentence
        all_sql = "\n".join(sql for sql, _ in executed)
        self.assertIn("INSERT INTO runs", all_sql)
        self.assertIn("INSERT INTO sentences", all_sql)
        self.assertIn("language_pair", all_sql)
        self.assertIn("tam_construction", all_sql)

    def test_repository_read_path_supports_dedup_and_metric_queries(self):
        from ela_pipeline.db.repository import PostgresContractRepository

        conn = _FakeConnection()
        conn.cursor_obj.fetchone_queue = [
            ("abc123", "She trusted him.", "en", "ru", "v1", "run-2"),
            (7,),
        ]

        repo = PostgresContractRepository(
            db_url="postgresql://local/test",
            connect_fn=lambda _db_url: conn,
        )

        row = repo.get_sentence_by_key("abc123")
        count = repo.count_sentences_by_language_pair("en", "ru")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["sentence_key"], "abc123")
        self.assertEqual(row["last_run_id"], "run-2")
        self.assertEqual(count, 7)

        all_sql = "\n".join(sql for sql, _ in conn.cursor_obj.calls)
        self.assertIn("SELECT sentence_key", all_sql)
        self.assertIn("COUNT(*)", all_sql)

    def test_upsert_sentence_uses_on_conflict_for_dedup(self):
        from ela_pipeline.db.repository import PostgresContractRepository

        conn = _FakeConnection()
        repo = PostgresContractRepository(
            db_url="postgresql://local/test",
            connect_fn=lambda _db_url: conn,
        )

        payload = {"type": "Sentence", "content": "She trusted him.", "linguistic_elements": []}
        ctx = {"cefr_provider": "t5"}
        repo.upsert_sentence(
            sentence_key="abc123",
            source_text="She trusted him.",
            source_lang="en",
            target_lang="ru",
            hash_version="v1",
            run_id="run-1",
            pipeline_context=ctx,
            contract_payload=payload,
        )
        repo.upsert_sentence(
            sentence_key="abc123",
            source_text="She trusted him.",
            source_lang="en",
            target_lang="ru",
            hash_version="v1",
            run_id="run-2",
            pipeline_context=ctx,
            contract_payload=payload,
        )

        all_sql = "\n".join(sql for sql, _ in conn.cursor_obj.calls)
        self.assertIn("ON CONFLICT (sentence_key)", all_sql)
