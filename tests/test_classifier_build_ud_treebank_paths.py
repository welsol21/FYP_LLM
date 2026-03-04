import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_ud_phase1_dataset import resolve_ud_split_map


class ResolveUDSplitMapTests(unittest.TestCase):
    def test_resolves_ewt_style_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "en_ewt-ud-train.conllu").write_text("", encoding="utf-8")
            (root / "en_ewt-ud-dev.conllu").write_text("", encoding="utf-8")
            (root / "en_ewt-ud-test.conllu").write_text("", encoding="utf-8")
            split_map = resolve_ud_split_map(str(root))
            self.assertTrue(split_map["train"].name.endswith("train.conllu"))
            self.assertTrue(split_map["dev"].name.endswith("dev.conllu"))
            self.assertTrue(split_map["test"].name.endswith("test.conllu"))

    def test_resolves_gum_style_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "en_gum-ud-train.conllu").write_text("", encoding="utf-8")
            (root / "en_gum-ud-dev.conllu").write_text("", encoding="utf-8")
            (root / "en_gum-ud-test.conllu").write_text("", encoding="utf-8")
            split_map = resolve_ud_split_map(str(root))
            self.assertEqual(split_map["train"].name, "en_gum-ud-train.conllu")
            self.assertEqual(split_map["dev"].name, "en_gum-ud-dev.conllu")
            self.assertEqual(split_map["test"].name, "en_gum-ud-test.conllu")


if __name__ == "__main__":
    unittest.main()
