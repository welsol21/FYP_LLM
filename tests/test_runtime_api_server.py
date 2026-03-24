import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import request as urlrequest
from unittest.mock import patch

from ela_pipeline.runtime import api_server


class RuntimeApiServerTests(unittest.TestCase):
    @patch(
        "ela_pipeline.runtime.api_server.os.path.isfile",
        side_effect=lambda path: (
            str(path).endswith("classifier_metadata.json")
            or str(path).endswith("best_tabular_cefr_baseline.joblib")
            or str(path).endswith("best_tabular_joint_profile.joblib")
        ),
    )
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=True)
    def test_resolve_classifier_settings_defaults_to_tabular_when_model_dir_exists(self, _mock_isdir, _mock_isfile):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "tabular")
        self.assertEqual(model_path, "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2")

    @patch("ela_pipeline.runtime.api_server.os.path.isfile", return_value=False)
    @patch("ela_pipeline.runtime.api_server.os.path.isdir", return_value=False)
    def test_resolve_classifier_settings_defaults_to_rule_when_no_deberta_dir(self, _mock_isdir, _mock_isfile):
        with patch.dict("os.environ", {}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "rule")
        self.assertIsNone(model_path)

    def test_resolve_classifier_settings_accepts_explicit_tabular_provider(self):
        with patch.dict("os.environ", {"ELA_CLASSIFIER_PROVIDER": "tabular"}, clear=False):
            provider, model_path = api_server._resolve_classifier_settings()
        self.assertEqual(provider, "tabular")
        self.assertEqual(model_path, "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2")

    def test_resolve_classifier_settings_rejects_invalid_provider(self):
        with patch.dict("os.environ", {"ELA_CLASSIFIER_PROVIDER": "invalid"}, clear=False):
            with self.assertRaisesRegex(ValueError, "ELA_CLASSIFIER_PROVIDER must be one of"):
                api_server._resolve_classifier_settings()

    @patch("ela_pipeline.runtime.api_server.SERVICE.build_sentence_contract")
    @patch(
        "ela_pipeline.runtime.api_server.os.path.isfile",
        side_effect=lambda path: (
            str(path).endswith("classifier_metadata.json")
            or str(path).endswith("best_tabular_cefr_baseline.joblib")
            or str(path).endswith("best_tabular_joint_profile.joblib")
        ),
    )
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
        self.assertEqual(kwargs["classifier_provider"], "tabular")
        self.assertEqual(kwargs["classifier_model_path"], "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2")

    @patch("ela_pipeline.runtime.api_server.SERVICE.build_sentence_contract")
    @patch(
        "ela_pipeline.runtime.api_server.os.path.isfile",
        side_effect=lambda path: (
            str(path).endswith("classifier_metadata.json")
            or str(path).endswith("best_tabular_cefr_baseline.joblib")
            or str(path).endswith("best_tabular_joint_profile.joblib")
        ),
    )
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
            self.assertEqual(kwargs["classifier_provider"], "tabular")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

class ApiServerHttpSmokeTests(unittest.TestCase):
    """Start a real ThreadingHTTPServer on a random port, hit all endpoints,
    verify they respond with 2xx JSON — not 502 / crash / connection-refused."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.RuntimeApiHandler)
        except PermissionError:
            cls.server = None
            return
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=2)

    def _get(self, path: str):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        with urlrequest.urlopen(f"{self.base}{path}", timeout=5) as r:  # nosec B310
            return r.status, json.loads(r.read().decode())

    def _post(self, path: str, body: dict):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        req = urlrequest.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=5) as r:  # nosec B310
            return r.status, json.loads(r.read().decode())

    def test_health_returns_200_ok(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "ok")

    @patch("ela_pipeline.runtime.api_server.SERVICE.get_ui_state", return_value={"mode": "offline"})
    def test_ui_state_returns_200(self, _mock):
        status, body = self._get("/api/ui-state")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, dict)

    @patch("ela_pipeline.runtime.api_server.SERVICE.get_visualizer_payload", return_value={})
    def test_visualizer_payload_missing_document_id_returns_empty(self, _mock):
        status, body = self._get("/api/visualizer-payload")
        self.assertEqual(status, 200)
        self.assertEqual(body, {})

    @patch("ela_pipeline.runtime.api_server.SERVICE.get_visualizer_payload", return_value={"s": "t"})
    def test_visualizer_payload_with_document_id_returns_200(self, _mock):
        status, body = self._get("/api/visualizer-payload?document_id=doc-123")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"s": "t"})

    @patch("ela_pipeline.runtime.api_server.SERVICE.get_backend_job_status", return_value={"status": "completed"})
    def test_backend_job_status_returns_200(self, _mock):
        status, body = self._get("/api/backend-job-status?job_id=local-abc")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "completed")

    def test_backend_job_status_missing_job_id_returns_400(self):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urlrequest.urlopen(f"{self.base}/api/backend-job-status", timeout=5)  # nosec B310
        self.assertEqual(ctx.exception.code, 400)

    @patch("ela_pipeline.runtime.api_server.SERVICE.list_document_artifacts", return_value=[])
    def test_document_artifacts_missing_id_returns_empty_list(self, _mock):
        status, body = self._get("/api/document-artifacts")
        self.assertEqual(status, 200)
        self.assertEqual(body, [])

    @patch("ela_pipeline.runtime.api_server.SERVICE.submit_media", return_value={"job_id": "local-xyz", "document_id": "doc-1"})
    def test_submit_media_returns_job_id(self, _mock):
        status, body = self._post("/api/submit-media", {"mediaPath": "/tmp/file.mp3", "durationSec": 60})
        self.assertEqual(status, 200)
        self.assertIn("job_id", body)

    def test_submit_media_missing_path_returns_400(self):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        import urllib.error
        req = urlrequest.Request(
            f"{self.base}/api/submit-media",
            data=json.dumps({}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urlrequest.urlopen(req, timeout=5)  # nosec B310
        self.assertEqual(ctx.exception.code, 400)

    @patch("ela_pipeline.runtime.api_server.SERVICE.cancel_backend_job", return_value={"status": "ok"})
    def test_cancel_job_returns_200(self, _mock):
        status, body = self._post("/api/cancel-job", {"job_id": "local-xyz"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    @patch("ela_pipeline.runtime.api_server.SERVICE.delete_analysis", return_value={"status": "ok"})
    def test_delete_analysis_returns_200(self, _mock):
        status, body = self._post("/api/delete-analysis", {"document_id": "doc-1"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_unknown_get_path_returns_404(self):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urlrequest.urlopen(f"{self.base}/api/nonexistent", timeout=5)  # nosec B310
        self.assertEqual(ctx.exception.code, 404)

    def test_unknown_post_path_returns_404(self):
        if not self.server:
            self.skipTest("Socket bind not permitted.")
        import urllib.error
        req = urlrequest.Request(
            f"{self.base}/api/nonexistent",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urlrequest.urlopen(req, timeout=5)  # nosec B310
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
