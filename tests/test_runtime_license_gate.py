import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime.license_gate import check_phonetic_license_gate, main


class RuntimeLicenseGateTests(unittest.TestCase):
    def _write_inventory(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return Path(tmp.name)

    def test_disabled_policy_passes(self):
        inventory = self._write_inventory("espeak-ng GPL-3.0")
        result = check_phonetic_license_gate(
            deployment_mode="local",
            phonetic_policy="disabled",
            legal_approval=False,
            inventory_path=inventory,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.code, "PASS_DISABLED")

    def test_distributed_requires_legal_approval(self):
        inventory = self._write_inventory("espeak-ng GPL-3.0")
        result = check_phonetic_license_gate(
            deployment_mode="distributed",
            phonetic_policy="enabled",
            legal_approval=False,
            inventory_path=inventory,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "LEGAL_APPROVAL_REQUIRED")

    def test_inventory_missing_fails(self):
        inventory = self._write_inventory("some other component")
        result = check_phonetic_license_gate(
            deployment_mode="backend",
            phonetic_policy="enabled",
            legal_approval=False,
            inventory_path=inventory,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "INVENTORY_MISSING_PHONETIC")

    def test_cli_emits_json_and_nonzero_on_fail(self):
        inventory = self._write_inventory("espeak-ng GPL-3.0")
        argv = [
            "license_gate",
            "--deployment-mode",
            "distributed",
            "--phonetic-policy",
            "enabled",
            "--inventory-path",
            str(inventory),
        ]
        with patch("sys.argv", argv):
            out = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stdout(out):
                    main()
        self.assertEqual(ctx.exception.code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
