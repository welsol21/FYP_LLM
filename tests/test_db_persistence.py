import unittest

from ela_pipeline.db.persistence import persist_inference_result


class _FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

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
