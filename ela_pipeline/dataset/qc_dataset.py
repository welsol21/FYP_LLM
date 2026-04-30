"""Comprehensive QC post-processor for the T5 ELA dataset.

Applies structural checks + 14 semantic gates to all.jsonl.
Writes:
  - qc_report.csv  — all rows with full QC annotation columns
  - clean.jsonl    — rows with qc_status in {ok, fixed}

Gates
-----
  0  Structural      : duplicate IDs, word content, target length, truncated sentences
  1  Conditional     : third conditional requires past-perfect if-clause + modal perfect result
  2  Passive         : detected passive tense must match target's claimed tense
  3  Imperative      : first-person label only for let's/let me/let us
  4  Reported        : statement / question / command subtype match
  5  Comparative     : irregular / periphrastic / -er / equality subtype match
  6  Shape           : isolated VP or fragment labelled as Sentence → auto-fix node_type
  7  Anchor          : key grammatical words claimed by target must appear in content/sentence
  8  OCR Artifact    : target starts with OCR corruption like (owever / (ere → drop
  9  NP Percentage   : percentage teaching note paired with non-percentage phrase → drop
  10 PP Tail         : content is 'of X' tail fragment → extend to full PP → fix_content
  11 Adv Mid-Pos     : mid-position adverb note but adverb is in end-position → drop
  12 Content Span    : Phrase/Word content not in sentence_text → fix spaces or manual_review
  13 Simple VP       : 'simple verb phrase' target paired with multi-word (complex) VP → manual

fix_action values : keep | fix_node_type | fix_content | drop | manual_review
qc_status values  : ok   | fixed | needs_manual_review | dropped

New QC columns
--------------
  actual_annotated_span : original content string before any content fix
  alignment_check       : True if content span found in sentence_text

Usage
-----
python -m ela_pipeline.dataset.qc_dataset \\
    --input-dir  /path/to/processed_t5_v35_book_pairs \\
    --output-dir /path/to/processed_t5_v35_book_pairs
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------

_ENDS_WITH_PUNCT = re.compile(r"[.!?]\s*$")

# Truncated relative clause
_TRUNCATED_RC_RE = re.compile(
    r"\b(who|which|that|whom)\s+"
    r"(is|are|was|were|had|have|has|will|would|can|could|may|might|shall|should)\s*$",
    re.I,
)

# Perfect modal: "would/could/might have" or contracted forms
_PERFECT_MODAL_RE = re.compile(
    r"\b(would|could|might|should)n?'?t?\s+have\b"
    r"|\bwould'?ve\b|\bcould'?ve\b|\bmight'?ve\b",
    re.I,
)

# Non-defining relative clause
_NON_DEFINING_RC_NOTE_RE = re.compile(
    r"\bnon.defining\b|\bnon.restrictive\b|\bsimply\s+gives\s+extra\s+information\b", re.I
)
_NON_DEFINING_RC_COMMA_RE = re.compile(r",\s*(who|which|whom|whose|that)\b", re.I)

# Preposition teaching anchor
_USE_BETWEEN_NOTE_RE = re.compile(r"\bbetween\s*\+\s*pronoun\b|\buse between\b", re.I)
_USE_AMONG_NOTE_RE = re.compile(r"\buse among\b", re.I)

# ---------------------------------------------------------------------------
# Gate 1 — Conditional
# ---------------------------------------------------------------------------

_THIRD_COND_NOTE_RE = re.compile(r"\bthird\s+conditional[s]?\b", re.I)


def _extract_if_clause(sentence: str) -> str:
    """Return the text of the if-clause (up to first comma or end of clause)."""
    m = re.search(r"\bif\b([^,;.!?]{2,100}?)(?:,|;|\s+then\b|$)", sentence, re.I | re.S)
    return m.group(1).strip() if m else ""


def _has_past_perfect_if(sentence: str) -> bool:
    """Check whether the if-clause contains a past perfect (had + word)."""
    if_clause = _extract_if_clause(sentence)
    if not if_clause:
        return False
    # "had" or "'d" as auxiliary past perfect
    return bool(re.search(r"\bhad(?:n'?t)?\s+\w+\b|\b'd\s+\w+\b", if_clause, re.I))


# ---------------------------------------------------------------------------
# Gate 2 — Passive pattern detection
# ---------------------------------------------------------------------------

def _detect_passive_pattern(text: str) -> str:
    """Return the detected passive pattern label, or '' if none detected."""
    t = text
    # Most specific patterns first (longer auxiliary chains)
    if re.search(r"\b(?:would|could|might|should|must|can|may)(?:n'?t)?\s+have\s+been\s+(?!\w+ing\b)\w+", t, re.I):
        return "modal_perfect_passive"
    if re.search(r"\b(?:am|is|are)\s+being\s+(?!\w+ing\b)\w+", t, re.I):
        return "present_continuous_passive"
    if re.search(r"\b(?:was|were)\s+being\s+(?!\w+ing\b)\w+", t, re.I):
        return "past_continuous_passive"
    if re.search(r"\bhad\s+been\s+(?!\w+ing\b)\w+", t, re.I):
        return "past_perfect_passive"
    if re.search(r"\b(?:has|have)\s+been\s+(?!\w+ing\b)\w+", t, re.I):
        return "present_perfect_passive"
    if re.search(r"\bwill\s+be\s+(?!\w+ing\b)\w+", t, re.I):
        return "future_passive"
    if re.search(r"\b(?:would|could|might|should|must|can|may)(?:n'?t)?\s+be\s+(?!\w+ing\b)\w+", t, re.I):
        return "modal_passive"
    # Simple passives — only match -ed/-en endings to avoid false positives
    if re.search(r"\b(?:am|is|are)\s+\w+(?:ed|en)\b", t, re.I):
        return "present_simple_passive"
    if re.search(r"\b(?:was|were)\s+\w+(?:ed|en)\b", t, re.I):
        return "past_simple_passive"
    return ""


def _target_passive_type(target: str) -> str:
    """Return the passive tense/type that the target text explicitly claims, or ''."""
    t = target
    if re.search(r"present\s+(?:continuous|progressive)\s+passive", t, re.I):
        return "present_continuous_passive"
    if re.search(r"past\s+(?:continuous|progressive)\s+passive", t, re.I):
        return "past_continuous_passive"
    if re.search(r"past\s+perfect\s+passive|had\s+been\s+\+", t, re.I):
        return "past_perfect_passive"
    if re.search(r"present\s+perfect\s+passive|(?:has|have)\s+been\s+\+", t, re.I):
        return "present_perfect_passive"
    if re.search(r"future\s+passive|will\s+be\s+\+\s*past\b|will\s+be\s+passive", t, re.I):
        return "future_passive"
    if re.search(r"modal\s+perfect\s+passive", t, re.I):
        return "modal_perfect_passive"
    if re.search(r"modal\s+passive|modal\s+\+\s*be\s+\+\s*past", t, re.I):
        return "modal_passive"
    if re.search(r"\bpast\s+(?:simple\s+)?passive\b|was/were\s+\+\s*past\b", t, re.I):
        return "past_simple_passive"
    if re.search(r"\bpresent\s+(?:simple\s+)?passive\b|is/are\s+\+\s*past\b|am/is/are\s+\+\s*past\b", t, re.I):
        return "present_simple_passive"
    return ""


# ---------------------------------------------------------------------------
# Gate 3 — Imperative subtype
# ---------------------------------------------------------------------------

_FIRST_PERSON_IMP_TARGET_RE = re.compile(
    r"\bfirst.person\s+(?:plural\s+)?imperative\b"
    r"|\bfirst.person\s+inclusive\b"
    r"|\blet'?s\b.{0,50}\bimperative\b"
    r"|\blet\s+(?:me|us)\b.{0,50}\bimperative\b",
    re.I,
)
_LETS_CONTENT_RE = re.compile(r"^\s*let(?:'s|\s+me|\s+us)\b", re.I)
_NEGATIVE_IMP_TARGET_RE = re.compile(r"\bnegative\s+imperative\b", re.I)
_NEGATIVE_IMP_CONTENT_RE = re.compile(r"^\s*(?:don'?t|do\s+not)\b", re.I)

# ---------------------------------------------------------------------------
# Gate 4 — Reported speech
# ---------------------------------------------------------------------------

_REPORTED_QUESTION_TARGET_RE = re.compile(
    r"\breported\s+question[s]?\b|\bindirect\s+question[s]?\b|\bembedded\s+question[s]?\b",
    re.I,
)
_REPORTED_STATEMENT_TARGET_RE = re.compile(
    r"\breported\s+statement[s]?\b|\bindirect\s+statement[s]?\b|\bindirect\s+speech\b.{0,40}\bstatement\b",
    re.I,
)
_WH_EMBEDDED_RE = re.compile(
    r"\b(?:how|what|where|when|why|whether)\s+\w|\bif\s+(?:he|she|it|they|I|we|you|the)\b",
    re.I,
)
# Reported statement markers: "that" + declarative clause
_THAT_DECL_RE = re.compile(r"\bthat\s+(?:he|she|it|they|I|we|you|the|a|an)\b", re.I)
# Reported command/request: to-infinitive (bare or after reporting verb)
_TO_INF_RE = re.compile(r"^\s*to\s+\w+\b", re.I)
_REPORTING_VERB_TO_RE = re.compile(
    r"\b(?:told|asked|ordered|requested|urged|begged|warned|advised|invited|persuaded"
    r"|reminded|helped|wanted|expected|required|forced|allowed|permitted)\b"
    r".{0,40}\bto\s+\w+",
    re.I,
)

# ---------------------------------------------------------------------------
# Gate 5 — Comparative subtype
# ---------------------------------------------------------------------------

_IRREGULAR_COMP_TARGET_RE = re.compile(
    r"\birregular\s+comparative[s]?\b|\birregular\s+form[s]?\b.{0,30}\bcomparative\b",
    re.I,
)
_ER_FORM_TARGET_RE = re.compile(
    r"\b-?er\s+form\b|\bends?\s+in\s+-?er\b|\bcomparative\s+form\b.{0,30}-?er\b|\bshort\s+comparative\b",
    re.I,
)
_EQUAL_COMP_TARGET_RE = re.compile(
    r"\bequal\s+comparison\b|\bequality\s+comparison\b|\bas\s+\.\.\.\s+as\b",
    re.I,
)
_PERIPHRASTIC_TARGET_RE = re.compile(
    r"\bmore\s+\+\s*(?:adjective|adverb)\b|\bperiphrastic\s+comparative\b|\bmore/less\b.{0,20}\bcomparative\b",
    re.I,
)
_MORE_LESS_CONTENT_RE = re.compile(r"^\s*(?:more|less)\s+\w+", re.I)
_KNOWN_IRREGULARS = frozenset({
    "better", "best", "worse", "worst", "further", "furthest",
    "farther", "farthest", "elder", "eldest", "less", "least",
})

# ---------------------------------------------------------------------------
# Gate 6 — Node type shape (isolated VP)
# ---------------------------------------------------------------------------

# Patterns that indicate an isolated verb phrase, not a full sentence
_ISOLATED_VP_RE = re.compile(
    r"^\s*(?:"
    r"(?:have|has|had)\s+been\s+\w+"      # have been found
    r"|will\s+be\s+\w+"                    # will be sent
    r"|(?:would|could|might|should|must|can|may)\s+be\s+\w+"  # modal + be + word
    r"|be(?:en)?\s+\w+(?:ed|en)\b"         # be/been + past participle
    r")",
    re.I,
)

# ---------------------------------------------------------------------------
# Gate 8 — OCR artifact in target
# ---------------------------------------------------------------------------

_OCR_ARTIFACT_TARGET_RE = re.compile(r"^\s*\((?:owever|ere)\b", re.I)

# ---------------------------------------------------------------------------
# Gate 9 — NP percentage mismatch
# ---------------------------------------------------------------------------

_PERCENTAGE_RE = re.compile(r"\b\d+\s*(?:percent|%)\b", re.I)

# ---------------------------------------------------------------------------
# Gate 10 — PP tail fragment
# ---------------------------------------------------------------------------

_PP_TAIL_RE = re.compile(r"^of\s+\w", re.I)

_PREPOSITIONS: frozenset = frozenset({
    "in", "on", "at", "to", "from", "by", "with", "into", "out", "up",
    "down", "over", "under", "through", "about", "after", "before",
    "between", "among", "for", "during", "until", "across", "along",
    "beyond", "outside", "inside", "toward", "towards", "upon", "onto",
    "off", "past", "round", "around", "near", "behind", "beside",
    "within", "without", "against", "throughout", "since",
})

# ---------------------------------------------------------------------------
# Gate 11 — Adverb mid-position alignment
# ---------------------------------------------------------------------------

_MID_POSITION_TARGET_RE = re.compile(
    r"\bmid.position\b|\bbetween\s+the\s+subject\s+and\b|\bbetween\s+auxiliary\s+and\b",
    re.I,
)
_SUBORD_CONJ_AFTER_RE = re.compile(
    r"^(?:when|while|because|if|although|though|once|until|before|after|since|as)\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Gate 12 — Content span normalization
# ---------------------------------------------------------------------------

_SPACE_COMMA_RE = re.compile(r"\s*,\s*")

# ---------------------------------------------------------------------------
# Gate 13 — Simple VP mismatch
# ---------------------------------------------------------------------------

_SIMPLE_VP_TARGET_RE = re.compile(r"\bsimple\s+verb\s+phrase\b", re.I)

# ---------------------------------------------------------------------------
# Gate 7 — Lexical anchors
# ---------------------------------------------------------------------------

# Anchor patterns: (target_pattern, content_check_fn, reason_label)
# Each tuple: if target matches, content/sentence must satisfy the check.
_ANCHOR_CHECKS: List[tuple] = [
    # "present continuous passive" → is/are being in sentence
    (
        re.compile(r"\bpresent\s+(?:continuous|progressive)\s+passive\b", re.I),
        lambda content, sentence: bool(re.search(r"\b(?:am|is|are)\s+being\b", sentence, re.I)),
        "anchor_present_cont_passive: no am/is/are being in sentence",
    ),
    # "future passive" → will be in sentence
    (
        re.compile(r"\bfuture\s+passive\b", re.I),
        lambda content, sentence: bool(re.search(r"\bwill\s+be\b", sentence, re.I)),
        "anchor_future_passive: no will be in sentence",
    ),
    # "first-person imperative" → let me/us/let's in content
    (
        _FIRST_PERSON_IMP_TARGET_RE,
        lambda content, sentence: bool(re.search(r"\blet(?:'s|\s+me|\s+us)\b", content, re.I)),
        "anchor_first_person_imp: no let me/us/let's in content",
    ),
    # "reported question" → wh-word or if/whether in content/sentence
    (
        _REPORTED_QUESTION_TARGET_RE,
        lambda content, sentence: bool(_WH_EMBEDDED_RE.search(content) or _WH_EMBEDDED_RE.search(sentence)),
        "anchor_reported_question: no wh-word or whether in content",
    ),
    # "unless" focused teaching note → unless in sentence
    (
        re.compile(r"\bunless\b.{0,60}\b(?:another|negative\s+conditional|conjunction)\b", re.I),
        lambda content, sentence: "unless" in sentence.lower(),
        "anchor_unless_focus: no unless in sentence",
    ),
]

# ---------------------------------------------------------------------------
# PP-tail and content-fix helpers
# ---------------------------------------------------------------------------

def _find_full_pp(content: str, sentence: str) -> Optional[str]:
    """Return the full PP (preposition + content) if content is a tail fragment.

    Scans up to 6 words before *content* in *sentence* for a preposition.
    Returns None when 'of' is the genuine head preposition (content is already a full PP).
    """
    idx = sentence.find(content)
    if idx < 0:
        return None
    before_words = sentence[:idx].split()
    if not before_words:
        return None
    for i in range(len(before_words) - 1, max(-1, len(before_words) - 6), -1):
        w = re.sub(r"[.,;:!?\"'()]", "", before_words[i]).lower()
        if w in _PREPOSITIONS:
            return " ".join(before_words[i:]) + " " + content
    return None


def _normalize_spaces(s: str) -> str:
    """Collapse spaces around commas to a single ', '."""
    return _SPACE_COMMA_RE.sub(", ", s).strip()


def _update_input_content(input_text: str, new_content: str) -> Optional[str]:
    """Return *input_text* with the payload 'content' field replaced by *new_content*."""
    if "payload: " not in input_text:
        return None
    prefix, payload_str = input_text.split("payload: ", 1)
    try:
        payload = json.loads(payload_str)
        payload["content"] = new_content
        return prefix + "payload: " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        return None


def _compute_alignment_check(row: Dict[str, Any]) -> bool:
    """True if content span is found inside sentence_text (Phrase/Word rows)."""
    if row.get("node_type") == "Sentence":
        return True
    content = _extract_content(row)
    sentence = row.get("sentence_text", "")
    return bool(content and sentence and content in sentence)


# ---------------------------------------------------------------------------
# Payload / content extraction
# ---------------------------------------------------------------------------

def _parse_payload(input_text: str) -> Optional[Dict[str, Any]]:
    try:
        payload_str = input_text.split("payload: ", 1)[1]
        return json.loads(payload_str)
    except Exception:
        return None


def _extract_content(row: Dict[str, Any]) -> str:
    """Return the human-readable content for this row."""
    node_type = row.get("node_type", "")
    if node_type == "Sentence":
        return row.get("sentence_text", "")
    payload = _parse_payload(row.get("input", ""))
    if payload:
        return payload.get("content", row.get("sentence_text", ""))
    return row.get("sentence_text", "")


def _get_service_field(row: Dict[str, Any], key: str, default: str = "") -> str:
    sf = row.get("service_fields") or {}
    if isinstance(sf, str):
        try:
            sf = json.loads(sf)
        except Exception:
            sf = {}
    return sf.get(key, default)


# ---------------------------------------------------------------------------
# Check functions
# Each returns None (ok) or Dict with keys: status, reason, fix_action, fixes
# ---------------------------------------------------------------------------

_STATUS_PRIORITY = {"ok": 0, "fixed": 1, "needs_manual_review": 2, "dropped": 3}


def _issue(status: str, reason: str, fix_action: str, fixes: Optional[Dict] = None) -> Dict:
    return {"status": status, "reason": reason, "fix_action": fix_action, "fixes": fixes or {}}


# -- Gate 0: structural --

def _chk_word_content(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Word":
        return None
    content = _extract_content(row)
    if " " in content.strip():
        return _issue("dropped", f"word_content_multiword: '{content}'", "drop")
    return None


def _chk_target_length(row: Dict) -> Optional[Dict]:
    target = row.get("target", "")
    if len(target.split()) < 5:
        return _issue("dropped", f"target_too_short: {len(target.split())} words", "drop")
    if not _ENDS_WITH_PUNCT.search(target):
        return _issue("needs_manual_review", "target_no_terminal_punct", "manual_review")
    return None


def _chk_truncated_sentence(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Sentence":
        return None
    sentence = row.get("sentence_text", "")
    if _TRUNCATED_RC_RE.search(sentence):
        return _issue("dropped", "truncated_sentence: ends mid-RC", "drop")
    return None


def _chk_non_defining_rc(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Sentence" or row.get("topic_key") != "relative_clauses":
        return None
    if _NON_DEFINING_RC_NOTE_RE.search(row.get("target", "")):
        if not _NON_DEFINING_RC_COMMA_RE.search(row.get("sentence_text", "")):
            return _issue("dropped", "non_defining_rc_note_but_no_comma_rc", "drop")
    return None


def _chk_between_among(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Phrase":
        return None
    target = row.get("target", "")
    content = _extract_content(row).lower()
    if _USE_BETWEEN_NOTE_RE.search(target) and "between" not in content:
        return _issue("needs_manual_review", "use_between_note_but_no_between_in_phrase", "manual_review")
    if _USE_AMONG_NOTE_RE.search(target) and "among" not in content:
        return _issue("needs_manual_review", "use_among_note_but_no_among_in_phrase", "manual_review")
    return None


def _chk_phrase_content_length(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Phrase":
        return None
    if len(_extract_content(row).strip()) < 2:
        return _issue("dropped", "phrase_content_too_short", "drop")
    return None


# -- Gate 1: conditional --

def _chk_conditional(row: Dict) -> Optional[Dict]:
    if row.get("topic_key") != "conditional_sentences":
        return None
    content = _extract_content(row)
    target = row.get("target", "")

    if not _THIRD_COND_NOTE_RE.search(target):
        return None

    # Wish / if-only structures are definitively not third conditional
    if re.search(r"\bwish\b|\bif\s+only\b", content, re.I):
        return _issue("dropped", "third_cond_target_but_wish/if_only_content", "drop")

    has_if = bool(re.search(r"\bif\b", content, re.I))

    if has_if:
        has_past_perfect_if = _has_past_perfect_if(content)
        has_modal_perfect = bool(_PERFECT_MODAL_RE.search(content))

        if not has_past_perfect_if and not has_modal_perfect:
            # No past perfect if-clause AND no modal perfect → clearly not third conditional
            return _issue(
                "dropped",
                "third_cond_mismatch: if-clause lacks past perfect and no would/could/might have",
                "drop",
            )
        if not has_past_perfect_if:
            # Has modal perfect (would have) but if-clause is past simple → mixed conditional
            return _issue(
                "dropped",
                "third_cond_mismatch: if-clause is past simple not past perfect (mixed conditional)",
                "drop",
            )
        if not has_modal_perfect:
            # Has past perfect if-clause but no modal perfect result → mixed conditional
            return _issue(
                "dropped",
                "third_cond_mismatch: no would/could/might have in result clause (mixed conditional)",
                "drop",
            )
    else:
        # No "if" at all. Inverted conditionals ("Had she known...") have "had" + perfect modal.
        # If neither is present, the content is clearly unrelated (passive, dialogue, simple sentence).
        if not re.search(r"\bhad\b", content, re.I) and not _PERFECT_MODAL_RE.search(content):
            return _issue(
                "dropped",
                "third_cond_mismatch: no if-clause, no had, no would/could/might have — not conditional",
                "drop",
            )

    return None


# -- Gate 2: passive pattern --

def _chk_passive_pattern(row: Dict) -> Optional[Dict]:
    """Check that target's claimed passive tense matches the actual passive pattern in content."""
    if row.get("topic_key") != "passive_voice":
        return None
    target = row.get("target", "")
    claimed = _target_passive_type(target)
    if not claimed:
        return None  # Target doesn't claim a specific tense — nothing to check

    content = _extract_content(row)
    actual = _detect_passive_pattern(content)
    if not actual:
        return None  # Can't detect pattern — don't flag

    if claimed != actual:
        return _issue(
            "needs_manual_review",
            f"passive_tense_mismatch: detected {actual}, target claims {claimed}",
            "manual_review",
        )
    return None


# -- Gate 3: imperative subtype --

def _chk_imperative(row: Dict) -> Optional[Dict]:
    if row.get("topic_key") != "imperative":
        return None
    content = _extract_content(row)
    target = row.get("target", "")

    # First-person imperative: content must start with let me / let us / let's
    if _FIRST_PERSON_IMP_TARGET_RE.search(target):
        if not _LETS_CONTENT_RE.match(content):
            return _issue(
                "dropped",
                "imperative_subtype_mismatch: first-person target but content is not let me/us/let's",
                "drop",
            )

    # Negative imperative: content should start with don't / do not
    if _NEGATIVE_IMP_TARGET_RE.search(target):
        if not _NEGATIVE_IMP_CONTENT_RE.match(content):
            return _issue(
                "needs_manual_review",
                "imperative_subtype_mismatch: negative target but content lacks don't/do not",
                "manual_review",
            )

    return None


# -- Gate 4: reported speech subtype --

def _chk_reported_speech(row: Dict) -> Optional[Dict]:
    if row.get("topic_key") != "reported_speech":
        return None
    content = _extract_content(row)
    target = row.get("target", "")

    # Reported question target but content is clearly a statement or command
    if _REPORTED_QUESTION_TARGET_RE.search(target):
        if not _WH_EMBEDDED_RE.search(content):
            # that-clause → clearly reported statement, not question
            if _THAT_DECL_RE.search(content):
                return _issue("dropped",
                              "reported_question_target_but_content_is_that_clause_statement", "drop")
            # to-infinitive (bare or after reporting verb) → clearly reported command/request
            if _TO_INF_RE.match(content) or _REPORTING_VERB_TO_RE.search(content):
                return _issue("dropped",
                              "reported_question_target_but_content_is_to_infinitive_command", "drop")
            return _issue("needs_manual_review",
                          "reported_question_target_but_no_wh_or_whether_in_content", "manual_review")

    # Reported statement target but content opens with a wh-word (clearly reported question)
    if _REPORTED_STATEMENT_TARGET_RE.search(target):
        if re.search(r"^\s*(?:how|what|where|when|why|whether)\b", content, re.I):
            return _issue("dropped",
                          "reported_statement_target_but_content_starts_with_wh_question", "drop")

    return None


# -- Gate 5: comparative subtype --

def _chk_comparative(row: Dict) -> Optional[Dict]:
    if row.get("topic_key") != "comparative_phrase":
        return None
    content = _extract_content(row)
    target = row.get("target", "")

    # Irregular comparative target but content is periphrastic (more/less + adj)
    if _IRREGULAR_COMP_TARGET_RE.search(target):
        if _MORE_LESS_CONTENT_RE.match(content):
            return _issue(
                "dropped",
                "comparative_mismatch: periphrastic more/less labelled as irregular comparative",
                "drop",
            )
        # Also check: content not in known irregular set (single-word form)
        words = set(content.lower().split())
        if len(words) == 1 and not (words & _KNOWN_IRREGULARS):
            return _issue(
                "needs_manual_review",
                "comparative_mismatch: target says irregular but no known irregular form detected",
                "manual_review",
            )

    # -er form target but content is periphrastic
    if _ER_FORM_TARGET_RE.search(target):
        if _MORE_LESS_CONTENT_RE.match(content):
            return _issue(
                "dropped",
                "comparative_mismatch: -er form target but content is more/less periphrastic",
                "drop",
            )

    # Equal comparison target but content is a more/less construction
    if _EQUAL_COMP_TARGET_RE.search(target):
        if _MORE_LESS_CONTENT_RE.match(content):
            return _issue(
                "dropped",
                "comparative_mismatch: equal (as...as) target but content is more/less",
                "drop",
            )

    return None


# -- Gate 6: node type / content shape --

def _chk_node_type_shape(row: Dict) -> Optional[Dict]:
    if row.get("node_type") != "Sentence":
        return None
    sentence = row.get("sentence_text", "")

    # Isolated VP pattern: starts with auxiliary chain, no subject before it
    if _ISOLATED_VP_RE.match(sentence) and len(sentence.split()) <= 7:
        return _issue(
            "fixed",
            "node_type_mismatch: isolated verb phrase labelled as Sentence → fixed to Phrase",
            "fix_node_type",
            {"node_type": "Phrase"},
        )

    return None


# -- Gate 7: lexical anchors --

def _chk_lexical_anchors(row: Dict) -> Optional[Dict]:
    content = _extract_content(row)
    sentence = row.get("sentence_text", "")
    target = row.get("target", "")
    reasons: List[str] = []

    for target_re, content_ok, reason_label in _ANCHOR_CHECKS:
        if target_re.search(target):
            if not content_ok(content, sentence):
                reasons.append(reason_label)

    if not reasons:
        return None
    return _issue("needs_manual_review", "; ".join(reasons), "manual_review")


# -- Gate 8: OCR artifact --

def _chk_ocr_artifact(row: Dict) -> Optional[Dict]:
    """Drop rows whose target begins with an OCR corruption marker."""
    if _OCR_ARTIFACT_TARGET_RE.match(row.get("target", "")):
        return _issue("dropped", f"ocr_artifact_target: {row.get('target','')[:40]!r}", "drop")
    return None


# -- Gate 9: NP percentage mismatch --

def _chk_np_percentage(row: Dict) -> Optional[Dict]:
    if row.get("topic_key") != "noun_phrase":
        return None
    target = row.get("target", "")
    if not _PERCENTAGE_RE.search(target):
        return None
    content = _extract_content(row)
    if not _PERCENTAGE_RE.search(content):
        return _issue("dropped", "np_percentage_mismatch: target mentions % but content lacks it", "drop")
    return None


# -- Gate 10: PP tail fragment --

def _chk_pp_tail(row: Dict) -> Optional[Dict]:
    """Extend 'of X' tail fragments to the full PP by prepending the head preposition."""
    if row.get("node_type") != "Phrase":
        return None
    content = _extract_content(row)
    if not _PP_TAIL_RE.match(content):
        return None
    sentence = row.get("sentence_text", "")
    full_pp = _find_full_pp(content, sentence)
    if full_pp and full_pp != content:
        new_input = _update_input_content(row.get("input", ""), full_pp)
        fixes: Dict[str, Any] = {"new_content": full_pp}
        if new_input:
            fixes["new_input"] = new_input
        return _issue("fixed", f"pp_tail_fragment: {content!r} → {full_pp!r}", "fix_content", fixes)
    return None  # 'of' is the genuine head preposition — content is already a full PP


# -- Gate 11: Adverb mid-position alignment --

def _chk_adv_mid_position(row: Dict) -> Optional[Dict]:
    """Drop rows where a mid-position adverb note is paired with an end-position adverb."""
    if row.get("topic_key") != "adverb_phrase":
        return None
    if not _MID_POSITION_TARGET_RE.search(row.get("target", "")):
        return None
    content = _extract_content(row)
    sentence = row.get("sentence_text", "")
    words = sentence.split()
    n = len(words)
    if n == 0:
        return None
    idx = next(
        (i for i, w in enumerate(words)
         if re.sub(r"[.,;:!?\"']", "", w).lower() == content.lower()),
        -1,
    )
    if idx < 0:
        return None  # Can't locate word — don't flag
    ratio = idx / n
    next_word = words[idx + 1] if idx + 1 < n else ""
    if ratio > 0.5 or _SUBORD_CONJ_AFTER_RE.match(next_word):
        return _issue(
            "dropped",
            f"adv_mid_position_mismatch: {content!r} at pos {idx}/{n} is end-position not mid",
            "drop",
        )
    return None


# -- Gate 12: Content span alignment --

def _chk_content_span(row: Dict) -> Optional[Dict]:
    """Phrase/Word content must appear in sentence_text.

    Tries a comma-space normalization fix first; otherwise flags for manual review.
    """
    if row.get("node_type") not in ("Phrase", "Word"):
        return None
    content = _extract_content(row)
    sentence = row.get("sentence_text", "")
    if not content or not sentence:
        return None
    if content in sentence:
        return None  # Exact match — fine
    norm_c = _normalize_spaces(content)
    norm_s = _normalize_spaces(sentence)
    if norm_c != content and norm_c in norm_s:
        new_input = _update_input_content(row.get("input", ""), norm_c)
        fixes: Dict[str, Any] = {"new_content": norm_c}
        if new_input:
            fixes["new_input"] = new_input
        return _issue("fixed", "content_span_space_fix: normalized comma-spaces in content", "fix_content", fixes)
    return _issue(
        "needs_manual_review",
        f"content_span_not_found: {content[:50]!r} not in sentence_text",
        "manual_review",
    )


# -- Gate 13: Simple VP mismatch --

def _chk_simple_vp_mismatch(row: Dict) -> Optional[Dict]:
    """Flag multi-word VP content paired with a 'simple verb phrase' target."""
    if row.get("topic_key") != "verb_phrase":
        return None
    if not _SIMPLE_VP_TARGET_RE.search(row.get("target", "")):
        return None
    content = _extract_content(row)
    if len(content.split()) >= 2:
        return _issue(
            "needs_manual_review",
            f"simple_vp_mismatch: target says simple VP but content is {content!r}",
            "manual_review",
        )
    return None


# ---------------------------------------------------------------------------
# All checks in application order
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    # Structural
    _chk_word_content,
    _chk_target_length,
    _chk_truncated_sentence,
    _chk_non_defining_rc,
    _chk_between_among,
    _chk_phrase_content_length,
    # Semantic
    _chk_conditional,        # Gate 1
    _chk_passive_pattern,    # Gate 2
    _chk_imperative,         # Gate 3
    _chk_reported_speech,    # Gate 4
    _chk_comparative,        # Gate 5
    _chk_node_type_shape,    # Gate 6
    _chk_lexical_anchors,    # Gate 7
    # Extended
    _chk_ocr_artifact,       # Gate 8
    _chk_np_percentage,      # Gate 9
    _chk_pp_tail,            # Gate 10
    _chk_adv_mid_position,   # Gate 11
    _chk_content_span,       # Gate 12
    _chk_simple_vp_mismatch, # Gate 13
]


def _run_checks(row: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all checks; return dict with status, reason, fix_action, fixes."""
    issues = [r for chk in ALL_CHECKS if (r := chk(row)) is not None]
    if not issues:
        return {"status": "ok", "reason": "", "fix_action": "keep", "fixes": {}}
    worst = max(issues, key=lambda x: _STATUS_PRIORITY.get(x["status"], 0))
    combined_reason = "; ".join(i["reason"] for i in issues)
    combined_fixes: Dict[str, Any] = {}
    for i in issues:
        combined_fixes.update(i.get("fixes") or {})
    return {
        "status": worst["status"],
        "reason": combined_reason,
        "fix_action": worst["fix_action"],
        "fixes": combined_fixes,
    }


# ---------------------------------------------------------------------------
# Duplicate ID detection
# ---------------------------------------------------------------------------

def _find_duplicate_ids(rows: List[Dict[str, Any]]) -> set:
    counts: Counter = Counter(r.get("id", "") for r in rows)
    return {id_ for id_, n in counts.items() if n > 1 and id_}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_qc(input_dir: Path, output_dir: Path, input_file: str = "all.jsonl") -> None:
    src = input_dir / input_file
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")

    rows: List[Dict[str, Any]] = []
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"Loaded {len(rows)} rows from {src}")

    dup_ids = _find_duplicate_ids(rows)
    if dup_ids:
        print(f"  Duplicate IDs: {len(dup_ids)} unique → "
              f"{sum(1 for r in rows if r.get('id') in dup_ids)} rows affected")

    seen_ids: set = set()
    qc_rows: List[Dict[str, Any]] = []

    for row in rows:
        row_id = row.get("id", "")
        original_content = _extract_content(row)
        original_node_type = row.get("node_type", "")
        original_target = row.get("target", "")

        # Duplicate: keep first, drop subsequent
        if row_id in dup_ids:
            if row_id in seen_ids:
                qc_rows.append({
                    **row,
                    "content": original_content,
                    "qc_status": "dropped",
                    "qc_reason": "duplicate_id",
                    "not_correct": 1,
                    "fix_action": "drop",
                    "original_content": "",
                    "original_node_type": "",
                    "original_target": "",
                })
                continue
        seen_ids.add(row_id)

        result = _run_checks(row)
        status = result["status"]
        fixes = result["fixes"]

        not_correct = 0 if status == "ok" else 1

        # Apply auto-fixes to a working copy
        working = dict(row)
        if fixes.get("node_type"):
            working["node_type"] = fixes["node_type"]
        if fixes.get("new_input"):
            working["input"] = fixes["new_input"]

        # Determine display content for CSV
        if fixes.get("new_content"):
            content_after = fixes["new_content"]
        elif fixes.get("node_type") == "Phrase" and row.get("node_type") == "Sentence":
            content_after = row.get("sentence_text", "")
        else:
            content_after = _extract_content(working)

        content_was_changed = bool(fixes.get("new_content") or fixes.get("node_type"))
        alignment_ok = _compute_alignment_check(row)

        qc_rows.append({
            **working,
            "content": content_after,
            "qc_status": status,
            "qc_reason": result["reason"],
            "not_correct": not_correct,
            "fix_action": result["fix_action"],
            "original_content": original_content if content_was_changed else "",
            "original_node_type": original_node_type if fixes.get("node_type") else "",
            "original_target": original_target if fixes.get("target") else "",
            "actual_annotated_span": original_content if fixes.get("new_content") else "",
            "alignment_check": alignment_ok,
        })

    # Summary
    status_counts = Counter(r["qc_status"] for r in qc_rows)
    reason_counts: Counter = Counter()
    for r in qc_rows:
        if r["qc_reason"]:
            for part in r["qc_reason"].split(";"):
                reason_counts[part.strip().split(":")[0]] += 1

    print(f"\nQC summary ({len(qc_rows)} rows):")
    for st in ("ok", "fixed", "needs_manual_review", "dropped"):
        print(f"  {st:22s}: {status_counts.get(st, 0)}")
    if reason_counts:
        print("\nReason breakdown (top issues):")
        for reason, n in reason_counts.most_common(20):
            print(f"  {n:4d}  {reason}")

    # Write QC report CSV
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "qc_report.csv"
    fieldnames = [
        "id", "qc_status", "qc_reason", "not_correct", "fix_action",
        "node_type", "topic_key", "source_id", "entry_head",
        "content", "sentence_text", "target",
        "original_content", "original_node_type", "original_target",
        "actual_annotated_span", "alignment_check",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in qc_rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"\nQC report written to: {csv_path}")

    # Write clean.jsonl + train/dev/test splits — ok + fixed rows, QC fields stripped
    _QC_FIELDS = {
        "content", "qc_status", "qc_reason", "not_correct", "fix_action",
        "original_content", "original_node_type", "original_target",
        "actual_annotated_span", "alignment_check",
    }
    clean_rows = [
        {k: v for k, v in r.items() if k not in _QC_FIELDS}
        for r in qc_rows
        if r["qc_status"] in {"ok", "fixed"}
    ]
    clean_path = output_dir / "clean.jsonl"
    with clean_path.open("w", encoding="utf-8") as f:
        for r in clean_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Clean dataset:   {clean_path}  ({len(clean_rows)} rows)")

    # Re-split: use _split tag from original build; fallback to all→train if missing
    split_rows: Dict[str, List] = {"train": [], "dev": [], "test": []}
    for r in clean_rows:
        split = r.get("_split", "train")
        split_rows.setdefault(split, []).append(r)

    for split_name, split_data in split_rows.items():
        split_path = output_dir / f"{split_name}.jsonl"
        with split_path.open("w", encoding="utf-8") as f:
            for r in split_data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    node_counts = Counter(r.get("node_type", "") for r in clean_rows)
    print(
        f"\nClean splits: train={len(split_rows['train'])}  "
        f"dev={len(split_rows['dev'])}  test={len(split_rows['test'])}"
    )
    print(f"Node types:   {dict(node_counts)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprehensive QC for T5 ELA dataset")
    parser.add_argument(
        "--input-dir",
        default="/home/vlad/Dev/FYP_LLM/data/processed_t5_v35_book_pairs",
    )
    parser.add_argument("--output-dir", default=None, help="Defaults to --input-dir")
    parser.add_argument("--input-file", default="all.jsonl")
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    run_qc(input_dir, output_dir, input_file=args.input_file)


if __name__ == "__main__":
    main()
