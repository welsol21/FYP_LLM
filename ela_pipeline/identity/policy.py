"""Phone-based minimal identity policy: normalize + hash, no raw phone persistence."""

from __future__ import annotations

import hashlib
import os
import re


_NON_DIGIT_RE = re.compile(r"[^\d+]")


def normalize_phone_e164(phone: str) -> str:
    """Normalize input into a strict E.164-like representation.

    Accepted:
    - leading '+' with digits
    - spaces, dashes, parentheses are ignored
    """

    raw = (phone or "").strip()
    if not raw:
        raise ValueError("Phone is required.")

    cleaned = _NON_DIGIT_RE.sub("", raw)
    if cleaned.count("+") > 1:
        raise ValueError("Invalid phone format.")

    if cleaned.startswith("+"):
        digits = cleaned[1:]
    else:
        digits = cleaned

    if not digits.isdigit():
        raise ValueError("Phone must contain digits only after normalization.")
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Phone length must be between 10 and 15 digits.")

    return f"+{digits}"


def phone_hash_salt_from_env() -> str:
    salt = os.getenv("ELA_PHONE_HASH_SALT", "").strip()
    if not salt:
        raise ValueError("ELA_PHONE_HASH_SALT must be configured.")
    return salt


def hash_phone_e164(phone_e164: str, *, salt: str) -> str:
    normalized = normalize_phone_e164(phone_e164)
    payload = f"{salt}:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
