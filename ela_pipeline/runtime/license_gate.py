"""Production license gate checks (focus: phonetic GPL-sensitive path)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .capabilities import resolve_deployment_mode


@dataclass(frozen=True)
class LicenseGateResult:
    ok: bool
    code: str
    message: str


def _inventory_has_phonetic_entries(inventory_path: Path) -> bool:
    if not inventory_path.exists():
        return False
    text = inventory_path.read_text(encoding="utf-8").lower()
    return "espeak-ng" in text and "gpl" in text


def check_phonetic_license_gate(
    *,
    deployment_mode: str,
    phonetic_policy: str,
    legal_approval: bool,
    inventory_path: Path,
) -> LicenseGateResult:
    mode = resolve_deployment_mode(deployment_mode)
    policy = (phonetic_policy or "").strip().lower()
    if policy not in {"enabled", "disabled", "backend_only"}:
        return LicenseGateResult(
            ok=False,
            code="INVALID_POLICY",
            message="phonetic_policy must be one of: enabled|disabled|backend_only",
        )

    if not _inventory_has_phonetic_entries(inventory_path):
        return LicenseGateResult(
            ok=False,
            code="INVENTORY_MISSING_PHONETIC",
            message="License inventory must explicitly include phonetic GPL component entries.",
        )

    if policy == "disabled":
        return LicenseGateResult(
            ok=True,
            code="PASS_DISABLED",
            message="Phonetic feature is disabled; GPL phonetic gate passed.",
        )

    if mode == "distributed":
        if not legal_approval:
            return LicenseGateResult(
                ok=False,
                code="LEGAL_APPROVAL_REQUIRED",
                message="Distributed deployment with phonetic enabled requires explicit legal approval.",
            )
        return LicenseGateResult(
            ok=True,
            code="PASS_DISTRIBUTED_APPROVED",
            message="Distributed deployment approved by legal gate.",
        )

    if mode == "local" and policy == "backend_only":
        return LicenseGateResult(
            ok=False,
            code="POLICY_MODE_CONFLICT",
            message="backend_only phonetic policy is incompatible with local deployment mode.",
        )

    return LicenseGateResult(
        ok=True,
        code="PASS",
        message="Phonetic license gate passed for current deployment mode.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run production license gate checks.")
    parser.add_argument("--feature", default="phonetic", choices=["phonetic"])
    parser.add_argument("--deployment-mode", default="auto", choices=["auto", "local", "backend", "distributed"])
    parser.add_argument("--phonetic-policy", default="enabled", choices=["enabled", "disabled", "backend_only"])
    parser.add_argument("--legal-approval", action="store_true", help="Set when formal legal review is approved.")
    parser.add_argument("--inventory-path", default="docs/licenses_inventory.md")
    args = parser.parse_args()

    result = check_phonetic_license_gate(
        deployment_mode=args.deployment_mode,
        phonetic_policy=args.phonetic_policy,
        legal_approval=bool(args.legal_approval),
        inventory_path=Path(args.inventory_path),
    )

    print(
        json.dumps(
            {
                "ok": result.ok,
                "code": result.code,
                "message": result.message,
            },
            ensure_ascii=False,
        )
    )
    if not result.ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
