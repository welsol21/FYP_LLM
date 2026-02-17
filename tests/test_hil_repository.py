import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.db.repository import PostgresContractRepository
from ela_pipeline.hil.export_feedback import apply_feedback_quality_gates, write_feedback_rows_to_jsonl


class _FakeCursor:
    def __init__(self):
        self.calls = []
        self.fetchone_queue = []
        self.fetchall_queue = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        if self.fetchone_queue:
            return self.fetchone_queue.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_queue:
            return self.fetchall_queue.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestHILRepository(unittest.TestCase):
    def test_create_add_list_export(self):
        conn = _FakeConnection()
        conn.cursor_obj.fetchone_queue = [(101,), (202,)]
        conn.cursor_obj.fetchall_queue = [
            [
                (101, "key-1", "reviewer", "fix", 0.9, 202, "n7", "cefr_level", "B1", "B2", "2026-02-17T00:00:00Z")
            ],
            [
                (
                    "key-1",
                    "reviewer",
                    "fix",
                    0.9,
                    {"provenance": {"source": "manual_review", "license": "internal_review"}},
                    "n7",
                    "cefr_level",
                    "B1",
                    "B2",
                    "2026-02-17T00:00:00Z",
                )
            ],
        ]
        repo = PostgresContractRepository(db_url="postgresql://local/test", connect_fn=lambda _db_url: conn)

        review_id = repo.create_review_event(sentence_key="key-1", reviewed_by="reviewer", change_reason="fix")
        edit_id = repo.add_node_edit(
            review_event_id=review_id,
            node_id="n7",
            field_path="cefr_level",
            before_value="B1",
            after_value="B2",
        )
        listed = repo.list_node_edits("key-1")
        exported = repo.export_feedback_rows(reviewed_by="reviewer", limit=5)

        self.assertEqual(review_id, 101)
        self.assertEqual(edit_id, 202)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["field_path"], "cefr_level")
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["after_value"], "B2")

    def test_write_feedback_rows_to_jsonl(self):
        rows = [
            {
                "sentence_key": "key-1",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "internal_review"}},
                "node_id": "n7",
                "field_path": "cefr_level",
                "before_value": "B1",
                "after_value": "B2",
                "edited_at": "2026-02-17T00:00:00Z",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "feedback.jsonl"
            count = write_feedback_rows_to_jsonl(rows, str(out))
            self.assertEqual(count, 1)
            payload = out.read_text(encoding="utf-8").strip()
            loaded = json.loads(payload)
            self.assertEqual(loaded["sentence_key"], "key-1")
            self.assertEqual(loaded["after_value"], "B2")

    def test_feedback_quality_gates_filter_and_dedup(self):
        rows = [
            {
                "sentence_key": "key-1",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "internal_review"}},
                "node_id": "n7",
                "field_path": "cefr_level",
                "before_value": "B1",
                "after_value": "B2",
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # duplicate of first row by dedup key
                "sentence_key": "key-1",
                "reviewed_by": "reviewer",
                "change_reason": "fix2",
                "confidence": 0.8,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "internal_review"}},
                "node_id": "n7",
                "field_path": "cefr_level",
                "before_value": "A2",
                "after_value": "B2",
                "edited_at": "2026-02-17T00:00:01Z",
            },
            {
                # invalid CEFR label
                "sentence_key": "key-2",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "internal_review"}},
                "node_id": "n8",
                "field_path": "cefr_level",
                "before_value": "B1",
                "after_value": "Z9",
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # invalid field path
                "sentence_key": "key-3",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "internal_review"}},
                "node_id": "n9",
                "field_path": "unknown_field",
                "before_value": "x",
                "after_value": "y",
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # invalid provenance license
                "sentence_key": "key-4",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "proprietary_unknown"}},
                "node_id": "n10",
                "field_path": "synonyms",
                "before_value": ["x"],
                "after_value": ["y"],
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # source/license mismatch
                "sentence_key": "key-5",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "manual_review", "license": "cc_by"}},
                "node_id": "n11",
                "field_path": "synonyms",
                "before_value": ["x"],
                "after_value": ["y"],
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # external license without source URL
                "sentence_key": "key-6",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {"provenance": {"source": "trusted_corpus", "license": "cc_by"}},
                "node_id": "n12",
                "field_path": "synonyms",
                "before_value": ["x"],
                "after_value": ["y"],
                "edited_at": "2026-02-17T00:00:00Z",
            },
            {
                # valid externally attributed row
                "sentence_key": "key-7",
                "reviewed_by": "reviewer",
                "change_reason": "fix",
                "confidence": 0.9,
                "review_metadata": {
                    "provenance": {
                        "source": "trusted_corpus",
                        "license": "cc_by",
                        "source_url": "https://example.org/source/1",
                    }
                },
                "node_id": "n13",
                "field_path": "synonyms",
                "before_value": ["x"],
                "after_value": ["y"],
                "edited_at": "2026-02-17T00:00:00Z",
            },
        ]
        filtered = apply_feedback_quality_gates(rows)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["sentence_key"], "key-1")
        self.assertEqual(filtered[1]["sentence_key"], "key-7")
