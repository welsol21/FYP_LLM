"""Validation helpers for canonical CEFR hierarchical corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True)
class CEFRCorpusValidationIssue:
    path: str
    message: str


def iter_contract_nodes(sentence: Dict[str, Any], *, sentence_index: int) -> Iterable[tuple[Dict[str, Any], str]]:
    sentence_path = f"[{sentence_index}]"
    yield sentence, sentence_path
    for phrase_index, phrase in enumerate(sentence.get("linguistic_elements", []) or []):
        if not isinstance(phrase, dict):
            continue
        phrase_path = f"{sentence_path}.linguistic_elements[{phrase_index}]"
        yield phrase, phrase_path
        for word_index, word in enumerate(phrase.get("linguistic_elements", []) or []):
            if not isinstance(word, dict):
                continue
            word_path = f"{phrase_path}.linguistic_elements[{word_index}]"
            yield word, word_path


def validate_cefr_corpus(payload: Any) -> List[CEFRCorpusValidationIssue]:
    issues: List[CEFRCorpusValidationIssue] = []

    if not isinstance(payload, list):
        return [CEFRCorpusValidationIssue(path="$", message="corpus must be a JSON array")]

    for sentence_index, sentence in enumerate(payload):
        if not isinstance(sentence, dict):
            issues.append(CEFRCorpusValidationIssue(path=f"[{sentence_index}]", message="sentence entry must be object"))
            continue
        for node, path in iter_contract_nodes(sentence, sentence_index=sentence_index):
            node_type = str(node.get("type") or "")
            if node_type not in {"Sentence", "Phrase", "Word"}:
                issues.append(CEFRCorpusValidationIssue(path=path, message=f"unexpected node type: {node_type!r}"))
            level = node.get("cefr_level")
            if not isinstance(level, str):
                issues.append(CEFRCorpusValidationIssue(path=f"{path}.cefr_level", message="missing cefr_level"))
                continue
            normalized = level.strip().upper()
            if normalized not in CEFR_LEVELS:
                issues.append(
                    CEFRCorpusValidationIssue(
                        path=f"{path}.cefr_level",
                        message=f"invalid cefr_level {level!r}; expected one of A1|A2|B1|B2|C1|C2",
                    )
                )
    return issues

