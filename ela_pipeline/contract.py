"""Contract helpers based on docs/sample.json."""

from __future__ import annotations

import copy
from typing import Any, Dict


def blank_node(node_type: str, content: str, part_of_speech: str, tense: str = "null") -> Dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        text = "-"
    return {
        "type": node_type,
        "content": content,
        "tense": tense,
        "aspect": "null",
        "mood": "null",
        "voice": "null",
        "finiteness": "null",
        "linguistic_notes": {
            "elementary": "",
            "intermediate": "",
            "advanced": "",
        },
        "schema_version": "v2",
        "part_of_speech": part_of_speech,
        "translations": {
            "backend_m2m100": {
                "source_lang": "en",
                "target_lang": "ru",
                "text": text,
            }
        },
        "active_translation_provider": "backend_m2m100",
        "linguistic_elements": [],
    }


def deep_copy_contract(data: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(data)
