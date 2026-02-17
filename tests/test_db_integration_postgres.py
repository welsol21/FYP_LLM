import os
import unittest
import uuid

from ela_pipeline.db.keys import build_sentence_key
from ela_pipeline.db.repository import PostgresContractRepository


class TestDBPostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_url = (
            os.getenv("ELA_TEST_DATABASE_URL", "").strip()
            or os.getenv("ELA_DATABASE_URL", "").strip()
            or os.getenv("DATABASE_URL", "").strip()
            or "postgresql://ela_user:ela_pass@localhost:5432/ela"
        )
        try:
            import psycopg

            cls._psycopg = psycopg
            with psycopg.connect(cls.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL integration DB is unavailable: {exc}") from exc

    def test_insert_dedup_and_query_metrics(self):
        repo = PostgresContractRepository(db_url=self.db_url)
        repo.ensure_schema()

        tag = uuid.uuid4().hex[:10]
        run_id_1 = f"itest-run-{tag}-1"
        run_id_2 = f"itest-run-{tag}-2"
        source_lang = f"en-it-{tag}"
        target_lang = f"ru-it-{tag}"
        sentence_text = f"Integration sentence {tag}."
        pipeline_context = {"provider": "integration-test", "tag": tag}

        sentence_key = build_sentence_key(
            sentence_text=sentence_text,
            source_lang=source_lang,
            target_lang=target_lang,
            pipeline_context=pipeline_context,
        )

        repo.upsert_run(run_id_1, {"tag": tag, "order": 1})
        repo.upsert_run(run_id_2, {"tag": tag, "order": 2})

        payload = {
            "type": "Sentence",
            "content": sentence_text,
            "tam_construction": "simple_past",
            "backoff_nodes_count": 0,
            "backoff_leaf_nodes_count": 0,
            "backoff_aggregate_nodes_count": 0,
            "backoff_unique_spans_count": 0,
            "linguistic_elements": [],
        }

        try:
            repo.upsert_sentence(
                sentence_key=sentence_key,
                source_text=sentence_text,
                source_lang=source_lang,
                target_lang=target_lang,
                hash_version="v1",
                run_id=run_id_1,
                pipeline_context=pipeline_context,
                contract_payload=payload,
                analytics={
                    "tam_construction": "simple_past",
                    "backoff_nodes_count": 0,
                    "backoff_leaf_nodes_count": 0,
                    "backoff_aggregate_nodes_count": 0,
                    "backoff_unique_spans_count": 0,
                },
            )
            # Dedup path: same key, new run id.
            repo.upsert_sentence(
                sentence_key=sentence_key,
                source_text=sentence_text,
                source_lang=source_lang,
                target_lang=target_lang,
                hash_version="v1",
                run_id=run_id_2,
                pipeline_context=pipeline_context,
                contract_payload=payload,
                analytics={
                    "tam_construction": "simple_past",
                    "backoff_nodes_count": 0,
                    "backoff_leaf_nodes_count": 0,
                    "backoff_aggregate_nodes_count": 0,
                    "backoff_unique_spans_count": 0,
                },
            )

            row = repo.get_sentence_by_key(sentence_key)
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["last_run_id"], run_id_2)
            self.assertEqual(row["source_lang"], source_lang)
            self.assertEqual(row["target_lang"], target_lang)

            # Unique language pair tag for this test -> must be exactly 1 row.
            pair_count = repo.count_sentences_by_language_pair(source_lang, target_lang)
            self.assertEqual(pair_count, 1)

            with self._psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM sentences WHERE sentence_key = %s", (sentence_key,))
                    exact_count = cur.fetchone()[0]
            self.assertEqual(exact_count, 1)
        finally:
            # Cleanup only test data.
            with self._psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sentences WHERE sentence_key = %s", (sentence_key,))
                    cur.execute("DELETE FROM runs WHERE run_id IN (%s, %s)", (run_id_1, run_id_2))
                conn.commit()
