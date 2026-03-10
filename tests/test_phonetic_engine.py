import os
import stat
import tempfile
import unittest

from ela_pipeline.phonetic.engine import EspeakPhoneticTranscriber


class PhoneticEngineTests(unittest.TestCase):
    def test_resolve_binary_accepts_executable_path(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            path = handle.name
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            resolved = EspeakPhoneticTranscriber._resolve_binary(path)
            self.assertEqual(resolved, path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_resolve_binary_rejects_non_executable_path(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            path = handle.name
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            with self.assertRaises(FileNotFoundError):
                EspeakPhoneticTranscriber._resolve_binary(path)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
