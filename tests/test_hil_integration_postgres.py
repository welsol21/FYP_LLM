import json
import os
import tempfile
import unittest
import uuid

from ela_pipeline.db.keys import build_sentence_key
from ela_pipeline.db.repository import PostgresContractRepository
from ela_pipeline.hil.export_feedback import export_feedback_to_jsonl


class TestHILIntegrationPostgres(unittest.TestCase):
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

    def test_hil_write_read_and_export_jsonl(self):
        repo = PostgresContractRepository(db_url=self.db_url)
        repo.ensure_schema()

        tag = uuid.uuid4().hex[:10]
        run_id = f"itest-hil-run-{tag}"
        source_lang = f"en-hil-{tag}"
        target_lang = f"ru-hil-{tag}"
        sentence_text = f"HIL integration sentence {tag}."
        ctx = {"provider": "hil-integration", "tag": tag}
        sentence_key = build_sentence_key(
            sentence_text=sentence_text,
            source_lang=source_lang,
            target_lang=target_lang,
            pipeline_context=ctx,
        )

        repo.upsert_run(run_id, {"tag": tag})
        repo.upsert_sentence(
            sentence_key=sentence_key,
            source_text=sentence_text,
            source_lang=source_lang,
            target_lang=target_lang,
            hash_version="v1",
            run_id=run_id,
            pipeline_context=ctx,
            contract_payload={"type": "Sentence", "content": sentence_text, "linguistic_elements": []},
            analytics={},
        )

        try:
            event_id = repo.create_review_event(
                sentence_key=sentence_key,
                reviewed_by="hil_tester",
                change_reason="manual_correction",
                confidence=0.95,
                metadata={"tag": tag},
            )
            repo.add_node_edit(
                review_event_id=event_id,
                node_id="n7",
                field_path="cefr_level",
                before_value="B1",
                after_value="B2",
            )
            # duplicate by dedup key: same sentence/node/field/after_value
            repo.add_node_edit(
                review_event_id=event_id,
                node_id="n7",
                field_path="cefr_level",
                before_value="A2",
                after_value="B2",
            )
            repo.add_node_edit(
                review_event_id=event_id,
                node_id="n7",
                field_path="synonyms",
                before_value=["trust"],
                after_value=["trust", "rely on"],
            )
            # invalid field path should be filtered out on export.
            repo.add_node_edit(
                review_event_id=event_id,
                node_id="n7",
                field_path="unsupported_field",
                before_value="x",
                after_value="y",
            )
            # invalid CEFR level should be filtered out on export.
            repo.add_node_edit(
                review_event_id=event_id,
                node_id="n7",
                field_path="cefr_level",
                before_value="B2",
                after_value="Z9",
            )

            edits = repo.list_node_edits(sentence_key)
            self.assertEqual(len(edits), 5)
            self.assertEqual(edits[0]["reviewed_by"], "hil_tester")

            exported = repo.export_feedback_rows(reviewed_by="hil_tester")
            tagged = [row for row in exported if row["sentence_key"] == sentence_key]
            self.assertEqual(len(tagged), 5)

            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "feedback.jsonl")
                written = export_feedback_to_jsonl(db_url=self.db_url, output_path=out, reviewed_by="hil_tester")
                # after quality gates + dedup we keep 2 rows (cefr_level=B2 and synonyms)
                self.assertEqual(written, 2)
                with open(out, "r", encoding="utf-8") as fh:
                    parsed = [json.loads(line) for line in fh if line.strip()]
                found = [row for row in parsed if row["sentence_key"] == sentence_key]
                self.assertEqual(len(found), 2)
        finally:
            with self._psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sentences WHERE sentence_key = %s", (sentence_key,))
                    cur.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
                conn.commit()
