import tempfile
import unittest
from pathlib import Path

from ela_pipeline.db.sqlite_repository import SQLiteContractRepository


class SQLiteContractRepositoryTests(unittest.TestCase):
    def test_upsert_and_read_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "backend.sqlite3")
            repo = SQLiteContractRepository(db_path)
            repo.ensure_schema()
            repo.upsert_run("run-1", {"tag": "t1"})
            repo.upsert_sentence(
                sentence_key="k1",
                source_text="She trusted him.",
                source_lang="en",
                target_lang="ru",
                hash_version="v1",
                run_id="run-1",
                pipeline_context={"mode": "test"},
                contract_payload={"type": "Sentence", "content": "She trusted him."},
                analytics={"tam_construction": "simple_past"},
            )

            row = repo.get_sentence_by_key("k1")
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["source_text"], "She trusted him.")
            self.assertEqual(repo.count_sentences_by_language_pair("en", "ru"), 1)

    def test_hil_rows_and_backend_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "backend.sqlite3")
            repo = SQLiteContractRepository(db_path)
            repo.ensure_schema()
            repo.upsert_run("run-1", {"tag": "t1"})
            repo.upsert_sentence(
                sentence_key="k1",
                source_text="She trusted him.",
                source_lang="en",
                target_lang="ru",
                hash_version="v1",
                run_id="run-1",
                pipeline_context={"mode": "test"},
                contract_payload={"type": "Sentence", "content": "She trusted him."},
            )

            review_id = repo.create_review_event(
                sentence_key="k1",
                reviewed_by="reviewer",
                change_reason="fix",
                confidence=0.9,
                metadata={"provenance": {"source": "manual_review", "license": "internal_review"}},
            )
            edit_id = repo.add_node_edit(
                review_event_id=review_id,
                node_id="n1",
                field_path="cefr_level",
                before_value="B1",
                after_value="B2",
            )
            self.assertGreater(edit_id, 0)

            listed = repo.list_node_edits("k1")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["after_value"], "B2")

            exported = repo.export_feedback_rows(reviewed_by="reviewer", limit=10)
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["field_path"], "cefr_level")

            account_id = repo.upsert_backend_account(phone_hash="abc_hash")
            self.assertGreater(account_id, 0)
            account = repo.get_backend_account_by_phone_hash(phone_hash="abc_hash")
            self.assertIsNotNone(account)
            assert account is not None
            self.assertEqual(account["phone_hash"], "abc_hash")


if __name__ == "__main__":
    unittest.main()
