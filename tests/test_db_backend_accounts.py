import unittest

from ela_pipeline.db.repository import PostgresContractRepository


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


class BackendAccountsRepositoryTests(unittest.TestCase):
    def test_upsert_and_get_backend_account(self):
        conn = _FakeConnection()
        conn.cursor_obj.fetchone_queue = [
            (42,),
            (42, "abc_hash", "2026-02-17T00:00:00Z", "2026-02-17T00:00:10Z"),
        ]
        repo = PostgresContractRepository(db_url="postgresql://local/test", connect_fn=lambda _url: conn)

        account_id = repo.upsert_backend_account(phone_hash="abc_hash")
        row = repo.get_backend_account_by_phone_hash(phone_hash="abc_hash")

        self.assertEqual(account_id, 42)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["id"], 42)
        self.assertEqual(row["phone_hash"], "abc_hash")

        all_sql = "\n".join(sql for sql, _ in conn.cursor_obj.calls)
        self.assertIn("INSERT INTO backend_accounts", all_sql)
        self.assertIn("ON CONFLICT (phone_hash)", all_sql)
        self.assertIn("SELECT id, phone_hash", all_sql)


if __name__ == "__main__":
    unittest.main()
