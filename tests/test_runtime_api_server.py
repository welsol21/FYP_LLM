import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import request as urlrequest
from unittest.mock import patch

from ela_pipeline.runtime import api_server


class RuntimeApiServerTests(unittest.TestCase):
    @patch("ela_pipeline.runtime.api_server.os.path.isfile", return_value=True)
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_resolve_classifier_settings_defaults_to_deberta_when_model_dir_exists(self, _mock_isdir, _mock_isfile):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "deberta")
        self.assertEqual(model_path, "artifacts/models/deberta_classifier_cefr")

    @patch("ela_pipeline.runtime.api_server.os.path.isfile", return_value=False)
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=False)
    def test_resolve_classifier_settings_defaults_to_rule_when_no_deberta_dir(self, _mock_isdir, _mock_isfile):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "rule")
        self.assertIsNone(model_path)

    def test_resolve_classifier_settings_rejects_invalid_provider(self):
        with patch.dict("os.environ", {"ELA_CLASSIFIER_PROVIDER": "invalid"}, clear=False):
            with self.assertRaisesRegex(ValueError, "ELA_CLASSIFIER_PROVIDER must be one of"):
                api_server._resolve_classifier_settings()

    @patch("ela_pipeline.runtime.api_server.SERVICE.build_sentence_contract")
    @patch("ela_pipeline.runtime.api_server.os.path.isfile", return_value=True)
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_build_sentence_contract_payload_uses_controlled_and_resolved_classifier(
        self,
        _mock_isdir,
        _mock_isfile,
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

    @patch("ela_pipeline.runtime.api_server.SERVICE.build_sentence_contract")
    @patch("ela_pipeline.runtime.api_server.os.path.isfile", return_value=True)
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_sentence_contract_http_e2e_smoke(self, _mock_isdir, _mock_isfile, mock_build_sentence_contract):
        mock_build_sentence_contract.return_value = {
            "sentence_text": "She trusted him.",
            "sentence_hash": "h-1",
            "sentence_node": {
                "type": "Sentence",
                "node_id": "n1",
                "content": "She trusted him.",
                "linguistic_elements": [],
                "linguistic_notes": ["Note"],
            },
        }

        with patch.dict("os.environ", {}, clear=False):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.RuntimeApiHandler)
            except PermissionError:
                self.skipTest("Socket bind is not permitted in current sandbox environment.")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            req = urlrequest.Request(
                f"http://{host}:{port}/api/sentence-contract",
                method="POST",
                data=json.dumps({"sentenceText": "She trusted him.", "sentenceIdx": 1}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(req, timeout=5) as resp:  # nosec B310
                body = json.loads(resp.read().decode("utf-8"))

            self.assertEqual(body["sentence_hash"], "h-1")
            self.assertEqual(body["sentence_node"]["type"], "Sentence")
            kwargs = mock_build_sentence_contract.call_args.kwargs
            self.assertEqual(kwargs["sentence_text"], "She trusted him.")
            self.assertEqual(kwargs["sentence_idx"], 1)
            self.assertEqual(kwargs["note_mode"], "controlled")
            self.assertEqual(kwargs["classifier_provider"], "deberta")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
