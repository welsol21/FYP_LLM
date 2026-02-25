import unittest
from unittest.mock import patch

from ela_pipeline.runtime import api_server


class RuntimeApiServerTests(unittest.TestCase):
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_resolve_classifier_settings_defaults_to_deberta_when_model_dir_exists(self, _mock_isdir):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "deberta")
        self.assertEqual(model_path, "artifacts/models/deberta_classifier_cefr")

    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=False)
    def test_resolve_classifier_settings_defaults_to_rule_when_no_deberta_dir(self, _mock_isdir):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "rule")
        self.assertIsNone(model_path)

    def test_resolve_classifier_settings_rejects_invalid_provider(self):
        with patch.dict("os.environ", {"ELA_CLASSIFIER_PROVIDER": "invalid"}, clear=False):
            with self.assertRaisesRegex(ValueError, "ELA_CLASSIFIER_PROVIDER must be one of"):
                api_server._resolve_classifier_settings()

    @patch("ela_pipeline.runtime.api_server.SERVICE.build_sentence_contract")
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_build_sentence_contract_payload_uses_controlled_and_resolved_classifier(
        self,
        _mock_isdir,
        mock_build_sentence_contract,
    ):
        mock_build_sentence_contract.return_value = {"ok": True}
        with patch.dict("os.environ", {}, clear=False):
            payload = api_server._build_sentence_contract_payload("She trusted him.", 2)
        self.assertEqual(payload, {"ok": True})
        kwargs = mock_build_sentence_contract.call_args.kwargs
        self.assertEqual(kwargs["note_mode"], "controlled")
        self.assertEqual(kwargs["classifier_provider"], "deberta")
        self.assertEqual(kwargs["classifier_model_path"], "artifacts/models/deberta_classifier_cefr")


if __name__ == "__main__":
    unittest.main()

