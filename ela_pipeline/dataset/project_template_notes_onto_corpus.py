"""Project templated book notes onto the natural ingested sentence corpus.

This produces a versioned enriched corpus where each sentence node from the
natural corpus carries:

- sentence note candidates matched by sentence family
- phrase note candidates matched by phrase family

The goal is to operationalize the workflow:
book notes -> family alignment -> templated transferable notes -> enriched corpus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.dataset.tree_construction_inventory import (
    _compress_phrase_signature_bucketed,
    _compress_phrase_signature_presence,
    _compress_sentence_signature_bucketed,
    _compress_sentence_signature_presence,
    _normalize_phrase_children,
    _phrase_signature,
    _sentence_signature,
)
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton

RELATIVE_MARKERS = {"who", "which", "that", "whom", "whose", "where", "when", "why"}
QUESTION_TAG_RE = re.compile(r",\s*[^,?!]{1,30}\?\s*$")
PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "between",
    "beyond",
    "by",
    "down",
    "during",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "out",
    "outside",
    "over",
    "past",
    "through",
    "to",
    "toward",
    "under",
    "up",
    "upon",
    "with",
    "within",
    "without",
}
AUXILIARY_FOR_TAG = {
    "am",
    "are",
    "is",
    "was",
    "were",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "will",
    "would",
    "can",
    "could",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "need",
    "ought",
    "won't",
    "wouldn't",
    "can't",
    "couldn't",
    "don't",
    "doesn't",
    "didn't",
    "haven't",
    "hasn't",
    "hadn't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "shouldn't",
    "mustn't",
}
TAG_PRONOUNS = {"i", "you", "he", "she", "it", "we", "they", "there"}
QUESTION_WORDS = {"what", "where", "when", "why", "who", "whom", "whose", "which", "how"}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _family_id(prefix: str, signature: Any) -> str:
    digest = hashlib.sha1(repr(signature).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: str, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _walk_nodes(node: dict[str, Any], parent: dict[str, Any] | None = None):
    yield node, parent
    for child in node.get("linguistic_elements") or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child, node)


def _build_phrase_entries(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]], parent_phrase_index: int | None = None) -> None:
        for child in nodes:
            exact_signature = _phrase_signature(child)
            entry_index = len(entries)
            entry = {
                "phrase_index": entry_index,
                "parent_phrase_index": parent_phrase_index,
                "content": _norm(child.get("content")),
                "part_of_speech": _norm(child.get("part_of_speech")).lower(),
                "grammatical_role": _norm(child.get("grammatical_role")).lower(),
                "source_span": child.get("source_span"),
                "exact_family_id": _family_id("phrase_exact", exact_signature),
                "bucketed_family_id": _family_id(
                    "phrase_bucket",
                    _compress_phrase_signature_bucketed(exact_signature),
                ),
                "presence_family_id": _family_id(
                    "phrase_presence",
                    _compress_phrase_signature_presence(exact_signature),
                ),
                "note_candidates": [],
                "children": [],
            }
            entries.append(entry)
            if parent_phrase_index is not None:
                entries[parent_phrase_index]["children"].append(entry_index)
            walk(child.get("children") or [], entry_index)

    walk(children)
    return entries


def _build_sentence_profiles(text: str, nlp: Any, *, max_phrase_depth: int) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for sentence_text, sentence_node in build_skeleton(text, nlp).items():
        effective_children = _normalize_phrase_children(
            sentence_node,
            depth=1,
            max_depth=max_phrase_depth,
            stats=Counter(),
        )
        exact_signature = _sentence_signature(effective_children)
        profiles.append(
            {
                "sentence_text": sentence_text,
                "source_span": sentence_node.get("source_span"),
                "voice": _norm(sentence_node.get("voice")).lower(),
                "grammar_classes": [_norm(item).lower() for item in sentence_node.get("grammar_classes") or [] if _norm(item)],
                "sentence_exact_family_id": _family_id("sent_exact", exact_signature),
                "sentence_bucketed_family_id": _family_id(
                    "sent_bucket",
                    _compress_sentence_signature_bucketed(exact_signature),
                ),
                "sentence_presence_family_id": _family_id(
                    "sent_presence",
                    _compress_sentence_signature_presence(exact_signature),
                ),
                "phrase_entries": _build_phrase_entries(effective_children),
            }
        )
    return profiles


def _note_payload(row: dict[str, Any], *, match_level: str) -> dict[str, Any]:
    projection = row.get("template_projection") or {}
    source = row.get("source") or {}
    target = row.get("target") or {}
    return {
        "match_level": match_level,
        "note_text": _norm(projection.get("rendered_note") or target.get("note_text")),
        "original_note_text": _norm(projection.get("original_note_text") or target.get("note_text")),
        "template_kind": _norm(projection.get("template_kind")),
        "templated": bool(projection.get("templated")),
        "risk_flags": list(projection.get("template_risk_flags") or []),
        "source_book": _norm(source.get("document_id")),
        "topic": _norm(source.get("topic")),
        "origin_unit": _norm(source.get("origin_unit")),
        "source_record_id": _norm(source.get("source_record_id")),
    }


def _tokenize_simple(text: str) -> list[str]:
    cleaned = re.sub(r"[\"'“”‘’]", "", text.lower())
    return re.findall(r"[a-z]+(?:n't)?", cleaned)


def _has_question_tag_pattern(text: str) -> bool:
    if "?" not in text or "," not in text:
        return False
    tail = text.rsplit(",", 1)[-1].strip()
    if not tail.endswith("?"):
        return False
    tokens = _tokenize_simple(tail[:-1])
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if tokens[-1] not in TAG_PRONOUNS:
        return False
    return any(token in AUXILIARY_FOR_TAG for token in tokens[:-1])


def _starts_with_yes_no_auxiliary(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(
        re.match(
            r"^(?:am|are|is|was|were|do|does|did|have|has|had|can|could|shall|should|will|would|may|might|must)\b",
            lowered,
        )
    ) and lowered.endswith("?")


def _starts_with_wh_question(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    first = lowered.split(" ", 1)[0].strip(" ?!.,;:")
    return first in QUESTION_WORDS and lowered.endswith("?")


def _looks_like_do_support_question(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^(?:do|does|did)\b", lowered)) and lowered.endswith("?")


def _looks_like_do_support_negative(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return any(token in lowered for token in (" do not ", " does not ", " did not ", " don't ", " doesn't ", " didn't "))


def _looks_like_negative_clause(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " not " in lowered or "n't " in lowered


def _looks_like_be_going_to(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return any(token in lowered for token in (" am going to ", " is going to ", " are going to "))


def _looks_like_future_time_clause(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    has_marker = any(token in lowered for token in (" before ", " after ", " when ", " while ", " until ", " as soon as "))
    has_future_main = any(token in lowered for token in (" will ", " shall ", " am going to ", " is going to ", " are going to "))
    return has_marker and has_future_main


def _looks_like_that_clause(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    matrix_verbs = (
        " know ",
        " knew ",
        " think ",
        " thought ",
        " hope ",
        " hoped ",
        " pretend ",
        " pretended ",
        " say ",
        " said ",
        " tell ",
        " told ",
        " suggest ",
        " suggested ",
        " agree ",
        " agreed ",
        " promise ",
        " promised ",
        " conclude ",
        " concluded ",
        " claim ",
        " claimed ",
        " assume ",
        " assumed ",
        " decide ",
        " decided ",
        " expect ",
        " expected ",
        " wish ",
        " wished ",
        " find ",
        " found ",
    )
    return " that " in lowered and any(token in lowered for token in matrix_verbs)


def _looks_like_shifted_that_clause(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^it\b.+\bthat\b", lowered))


def _looks_like_wh_noun_clause(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    patterns = (
        r"\b(?:know|knew|learn|learned|wonder|wondered|see|saw|tell|told|guess|guessed|discover|discovered|remember|remembered|understand|understood|find out|found out|ask|asked|worry about|worried about)\b.+\b(?:what|where|when|why|who|whom|whose|which|how)\b",
        r"^(?:what|whatever|who|whom|whose|which|where|when|why|how)\b.+\b(?:is|was|remains|seems)\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns) and not lowered.endswith("?")


def _looks_like_existential_there_question(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^(?:is|are|was|were)\s+there\b", lowered)) and lowered.endswith("?")


def _has_conditional_marker(text: str) -> bool:
    lowered = f" {_norm(text).lower()} "
    markers = (
        " if ",
        " unless ",
        " provided ",
        " providing ",
        " as long as ",
        " so long as ",
        " only if ",
        " even if ",
        " whether or not ",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_it_cleft(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(
        re.match(r"^it\s+(?:is|was|['`]s)\s+.+\s+(?:who|that|when)\b", lowered)
    )


def _looks_like_wh_cleft(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    if lowered.startswith("what "):
        return bool(
            re.match(
                r"^what\s+.+\b(?:do|did|does|want|wanted|need|needed|impressed|appealed|have to do|has to do)\b.+\b(?:is|was)\b",
                lowered,
            )
        )
    if lowered.startswith("all "):
        return bool(
            re.match(
                r"^all\s+.+\b(?:do|did|does|want|wanted|need|needed)\b.+\b(?:is|was)\b",
                lowered,
            )
        )
    return False


def _looks_like_modal_main_conditional(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " if " in lowered and any(token in lowered for token in (" would ", " should ", " could ", " might ", " can ", " may ", " must ")) and " would have " not in lowered and " could have " not in lowered and " should have " not in lowered and " might have " not in lowered


def _looks_like_extraposition_it(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    if not re.match(
        r"^it\s+(?:is|was|['`]s|seems|seemed|appears|appeared|became|becomes|become|costs|takes|took|took|finds|found|thinks|thought|pleases|pleased|shocks|shocked|interests|interested|bothers|bothered|matters|mattered|won't surprise|will surprise|doesn't matter)\b",
        lowered,
    ):
        return False
    return any(marker in lowered for marker in (" that ", " to ", " when ", " if "))


def _starts_with_existential_there(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(
        re.match(
            r"^there\s+(?:is|are|was|were|['`]s|has been|have been|had been|will be|would be|can be|could be|may be|might be|must be|seems(?:\s+to\s+be)?|appear(?:s)?\s+to\s+be|remains?|remained|followed|comes|come|happened\s+to\s+be|tend(?:s)?\s+to\s+be|is\s+said\s+to\s+be|is\s+expected\s+to\s+be)\b",
            lowered,
        )
    )


def _looks_like_first_conditional(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " if " in lowered and any(token in lowered for token in (" will ", " shall ", " 'll "))


def _looks_like_second_conditional(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " if " in lowered and any(token in lowered for token in (" would ", " should ", " could ", " might ")) and " would have " not in lowered and " could have " not in lowered and " should have " not in lowered and " might have " not in lowered


def _looks_like_third_conditional(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " if " in lowered and " had " in lowered and any(token in lowered for token in (" would have ", " could have ", " should have ", " might have "))


def _looks_like_zero_conditional(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    if " if " not in lowered:
        return False
    blocked = (" will ", " shall ", " would ", " should ", " could ", " might ", " had ", " have ")
    return not any(token in lowered for token in blocked)


def _looks_like_formal_should_conditional(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.search(r"\bif\b.+\bshould\b", lowered)) or bool(re.match(r"^should\b.+,", lowered))


def _looks_like_were_to_conditional(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.search(r"\bif\b.+\bwere to\b", lowered))


def _looks_like_inverted_conditional(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^(?:should|were|had)\b.+,", lowered))


def _looks_like_reduced_if_phrase(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    if not re.match(r"^if\b.+,", lowered):
        return False
    if any(token in lowered for token in (" is ", " are ", " was ", " were ", " has ", " have ", " had ")):
        return False
    return len(lowered.split(",", 1)[0].split()) <= 4


def _looks_like_necessary_condition(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return any(token in lowered for token in (" provided ", " providing ", " as long as ", " so long as ", " only if "))


def _looks_like_even_if(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " even if " in lowered


def _looks_like_passive_reporting_it(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^it\s+(?:is|was|has been|had been)\s+(?:agreed|felt|found|rumoured|rumored|said|thought|believed)\s+that\b", lowered))


def _looks_like_passive_by_phrase(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " by " in lowered


def _looks_like_passive_with_instrument(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return " with " in lowered


def _looks_like_passive_by_ing(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.search(r"\bby\s+[a-z-]+ing\b", lowered))


def _looks_like_state_passive_with_with(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return any(token in lowered for token in (" was ", " were ", " is ", " are ")) and " with " in lowered


def _looks_like_lexical_passive(text: str) -> bool:
    lowered = " " + _norm(text).lower().replace("’", "'") + " "
    return any(token in lowered for token in (" scheduled ", " deemed ", " alleged ", " acclaimed ", " dubbed "))


def _looks_like_impersonal_it_weather(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    weather_markers = (
        "it's raining",
        "it is raining",
        "it was raining",
        "it's snowing",
        "it is snowing",
        "it's windy",
        "it is windy",
        "it's cold",
        "it is cold",
        "it's hot",
        "it is hot",
        "it's dark",
        "it is dark",
    )
    return any(lowered.startswith(marker) for marker in weather_markers)


def _looks_like_impersonal_it_time(text: str) -> bool:
    lowered = _norm(text).lower().replace("’", "'")
    return bool(re.match(r"^it\s+(?:is|was|['`]s)\s+(?:\d|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered))


def _contains_relative_marker(text: str) -> bool:
    tokens = {token.strip(".,;:!?()[]{}\"'").lower() for token in text.split()}
    return any(token in RELATIVE_MARKERS for token in tokens)


def _starts_with_preposition_marker(text: str) -> bool:
    tokens = [token.strip(".,;:!?()[]{}\"'").lower() for token in text.split()]
    if len(tokens) < 2:
        return False
    return tokens[0] in PREPOSITIONS and tokens[1] in RELATIVE_MARKERS


def _sentence_candidate_compatible(note_row: dict[str, Any], profile: dict[str, Any]) -> bool:
    topic = _norm(((note_row.get("source") or {}).get("topic"))).lower()
    sentence_text = _norm(profile.get("sentence_text")).lower()
    grammar_classes = set(profile.get("grammar_classes") or [])
    voice = _norm(profile.get("voice")).lower()

    if topic == "general passive voice":
        return voice == "passive" or "passive_voice" in grammar_classes
    if topic == "passive form":
        return voice == "passive" or "passive_voice" in grammar_classes
    if topic == "passive without performer":
        return (voice == "passive" or "passive_voice" in grammar_classes) and not _looks_like_passive_by_phrase(sentence_text)
    if topic == "passive reporting it structure":
        return _looks_like_passive_reporting_it(sentence_text)
    if topic == "passive by phrase":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_by_phrase(sentence_text)
    if topic == "passive with instrument":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_with_instrument(sentence_text)
    if topic == "passive by ing method":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_by_ing(sentence_text)
    if topic == "state passive with with":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_state_passive_with_with(sentence_text)
    if topic == "lexically common passive":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_lexical_passive(sentence_text)
    if "question tag" in topic:
        return _has_question_tag_pattern(sentence_text)
    if topic == "yes-no question" or topic == "yes-no question with be":
        return _starts_with_yes_no_auxiliary(sentence_text)
    if topic == "do-support yes-no question":
        return _looks_like_do_support_question(sentence_text)
    if topic == "wh-question" or topic == "wh-question with do-support":
        return _starts_with_wh_question(sentence_text)
    if topic == "negative clause":
        return _looks_like_negative_clause(sentence_text)
    if topic == "do-support negative clause":
        return _looks_like_do_support_negative(sentence_text)
    if topic == "general conditional clause":
        return _has_conditional_marker(sentence_text)
    if topic == "unless clause":
        return " unless " in f" {sentence_text} "
    if topic == "if clause consequence":
        return " if " in f" {sentence_text} "
    if topic == "first conditional":
        return _looks_like_first_conditional(sentence_text)
    if topic == "second conditional" or topic == "unlikely conditional":
        return _looks_like_second_conditional(sentence_text)
    if topic == "third conditional" or topic == "counterfactual past conditional":
        return _looks_like_third_conditional(sentence_text)
    if topic == "zero conditional":
        return False
    if topic == "present possibility conditional":
        return _looks_like_modal_main_conditional(sentence_text)
    if topic == "future conditional":
        return _looks_like_first_conditional(sentence_text)
    if topic == "formal should conditional":
        return _looks_like_formal_should_conditional(sentence_text)
    if topic == "were-to conditional":
        return _looks_like_were_to_conditional(sentence_text)
    if topic == "inverted conditional":
        return _looks_like_inverted_conditional(sentence_text)
    if topic == "reduced if phrase":
        return _looks_like_reduced_if_phrase(sentence_text)
    if topic == "necessary-condition clause":
        return _looks_like_necessary_condition(sentence_text)
    if topic == "even if clause":
        return _looks_like_even_if(sentence_text)
    if topic == "it cleft" or topic == "it cleft adverbial focus" or topic == "it time-focus split sentence":
        return _looks_like_it_cleft(sentence_text)
    if topic == "what cleft action" or topic == "what cleft need/want" or topic == "all cleft":
        return _looks_like_wh_cleft(sentence_text)
    if topic == "impersonal it weather":
        return _looks_like_impersonal_it_weather(sentence_text)
    if topic == "impersonal it time":
        return _looks_like_impersonal_it_time(sentence_text)
    if topic == "impersonal it place or situation":
        return False
    if topic == "it extraposition to infinitive":
        return _looks_like_extraposition_it(sentence_text) and " to " in f" {sentence_text} "
    if topic == "it extraposition that clause":
        return _looks_like_extraposition_it(sentence_text) and " that " in f" {sentence_text} "
    if topic == "it with take or cost":
        return bool(re.match(r"^it\s+(?:takes|took|costs|cost)\b", sentence_text))
    if topic == "anticipatory object it":
        return bool(re.search(r"\b(?:find|found|think|thought)\s+it\s+[a-z-]+\s+(?:to|that)\b", sentence_text))
    if topic == "be going to future" or topic == "be going to future negative":
        return _looks_like_be_going_to(sentence_text) and not sentence_text.endswith("?")
    if topic == "be going to yes-no question" or topic == "be going to wh-question":
        return _looks_like_be_going_to(sentence_text) and sentence_text.endswith("?")
    if topic == "future time clause":
        return _looks_like_future_time_clause(sentence_text)
    if topic == "that-clause noun clause" or topic == "deleted-that clause":
        return _looks_like_that_clause(sentence_text)
    if topic == "shifted that-clause":
        return _looks_like_shifted_that_clause(sentence_text)
    if topic == "wh-clause noun clause" or topic == "wh-clause noun clause formal":
        return _looks_like_wh_noun_clause(sentence_text)
    if topic == "existential there yes-no question":
        return _looks_like_existential_there_question(sentence_text)
    if topic == "maybe adverb":
        return sentence_text.startswith("maybe ")
    if topic == "existential there basic":
        return _starts_with_existential_there(sentence_text)
    if topic == "existential there event":
        return False
    if topic == "existential there with ing":
        return _starts_with_existential_there(sentence_text) and bool(re.search(r"\bthere\s+(?:is|are|was|were)\b.+\b[a-z-]+ing\b", sentence_text))
    if topic == "existential there agreement":
        return _starts_with_existential_there(sentence_text)
    if topic == "existential there with seem or appear":
        return bool(re.match(r"^there\s+(?:seems?|appears?)\b", sentence_text))
    if topic == "existential there with passive reporting verb":
        return bool(re.match(r"^there\s+is\s+(?:said|expected|thought|believed)\s+to\s+be\b", sentence_text))
    if topic == "existential there formal literary":
        return bool(re.match(r"^there\s+(?:remains?|remained|followed|comes|come)\b", sentence_text))
    if "split sentence" in topic or "cleft" in topic:
        return _looks_like_it_cleft(sentence_text) or _looks_like_wh_cleft(sentence_text)
    if "impersonal it" in topic or "extraposition it" in topic:
        return _looks_like_extraposition_it(sentence_text)
    if "existential there" in topic:
        return _starts_with_existential_there(sentence_text)
    return True


def _source_sentence_note_usable(row: dict[str, Any]) -> bool:
    context = row.get("context") or {}
    topic = _norm(((row.get("source") or {}).get("topic"))).lower()
    note_text = _norm(((row.get("template_projection") or {}).get("rendered_note")))
    sentence_text = _norm(context.get("sentence_text") or context.get("content"))
    grammar_classes = {_norm(item).lower() for item in context.get("grammar_classes") or [] if _norm(item)}
    voice = _norm(context.get("voice")).lower()

    if topic == "general passive voice":
        return (voice == "passive" or "passive_voice" in grammar_classes) and "passive" in note_text.lower()
    if topic == "passive form":
        return voice == "passive" or "passive_voice" in grammar_classes
    if topic == "passive without performer":
        return (voice == "passive" or "passive_voice" in grammar_classes) and not _looks_like_passive_by_phrase(sentence_text)
    if topic == "passive reporting it structure":
        return _looks_like_passive_reporting_it(sentence_text)
    if topic == "passive by phrase":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_by_phrase(sentence_text)
    if topic == "passive with instrument":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_with_instrument(sentence_text)
    if topic == "passive by ing method":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_passive_by_ing(sentence_text)
    if topic == "state passive with with":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_state_passive_with_with(sentence_text)
    if topic == "lexically common passive":
        return (voice == "passive" or "passive_voice" in grammar_classes) and _looks_like_lexical_passive(sentence_text)
    if "question tag" in topic:
        if not _has_question_tag_pattern(sentence_text):
            return False
        lowered = note_text.lower()
        return "question tag" in lowered and "have you?" not in lowered and "wasn’t it?" not in lowered and "wasn't it?" not in lowered
    if topic == "yes-no question" or topic == "yes-no question with be":
        return _starts_with_yes_no_auxiliary(sentence_text)
    if topic == "do-support yes-no question":
        return _looks_like_do_support_question(sentence_text)
    if topic == "wh-question" or topic == "wh-question with do-support":
        return _starts_with_wh_question(sentence_text)
    if topic == "negative clause":
        return _looks_like_negative_clause(sentence_text)
    if topic == "do-support negative clause":
        return _looks_like_do_support_negative(sentence_text)
    if topic == "general conditional clause":
        return _has_conditional_marker(sentence_text)
    if topic == "unless clause":
        return " unless " in f" {sentence_text} "
    if topic == "if clause consequence":
        return " if " in f" {sentence_text} "
    if topic == "first conditional":
        return _looks_like_first_conditional(sentence_text)
    if topic == "second conditional" or topic == "unlikely conditional":
        return _looks_like_second_conditional(sentence_text)
    if topic == "third conditional" or topic == "counterfactual past conditional":
        return _looks_like_third_conditional(sentence_text)
    if topic == "zero conditional":
        return False
    if topic == "present possibility conditional":
        return _looks_like_modal_main_conditional(sentence_text)
    if topic == "future conditional":
        return _looks_like_first_conditional(sentence_text)
    if topic == "formal should conditional":
        return _looks_like_formal_should_conditional(sentence_text)
    if topic == "were-to conditional":
        return _looks_like_were_to_conditional(sentence_text)
    if topic == "inverted conditional":
        return _looks_like_inverted_conditional(sentence_text)
    if topic == "reduced if phrase":
        return _looks_like_reduced_if_phrase(sentence_text)
    if topic == "necessary-condition clause":
        return _looks_like_necessary_condition(sentence_text)
    if topic == "even if clause":
        return _looks_like_even_if(sentence_text)
    if topic == "it cleft" or topic == "it cleft adverbial focus" or topic == "it time-focus split sentence":
        return _looks_like_it_cleft(sentence_text)
    if topic == "what cleft action" or topic == "what cleft need/want" or topic == "all cleft":
        return _looks_like_wh_cleft(sentence_text)
    if topic == "impersonal it weather":
        return _looks_like_impersonal_it_weather(sentence_text)
    if topic == "impersonal it time":
        return _looks_like_impersonal_it_time(sentence_text)
    if topic == "impersonal it place or situation":
        return False
    if topic == "it extraposition to infinitive":
        return _looks_like_extraposition_it(sentence_text) and " to " in f" {sentence_text} "
    if topic == "it extraposition that clause":
        return _looks_like_extraposition_it(sentence_text) and " that " in f" {sentence_text} "
    if topic == "it with take or cost":
        return bool(re.match(r"^it\s+(?:takes|took|costs|cost)\b", sentence_text))
    if topic == "anticipatory object it":
        return bool(re.search(r"\b(?:find|found|think|thought)\s+it\s+[a-z-]+\s+(?:to|that)\b", sentence_text))
    if topic == "be going to future" or topic == "be going to future negative":
        return _looks_like_be_going_to(sentence_text) and not sentence_text.endswith("?")
    if topic == "be going to yes-no question" or topic == "be going to wh-question":
        return _looks_like_be_going_to(sentence_text) and sentence_text.endswith("?")
    if topic == "future time clause":
        return _looks_like_future_time_clause(sentence_text)
    if topic == "that-clause noun clause" or topic == "deleted-that clause":
        return _looks_like_that_clause(sentence_text)
    if topic == "shifted that-clause":
        return _looks_like_shifted_that_clause(sentence_text)
    if topic == "wh-clause noun clause" or topic == "wh-clause noun clause formal":
        return _looks_like_wh_noun_clause(sentence_text)
    if topic == "existential there yes-no question":
        return _looks_like_existential_there_question(sentence_text)
    if topic == "maybe adverb":
        return sentence_text.startswith("maybe ")
    if topic == "existential there basic":
        return _starts_with_existential_there(sentence_text)
    if topic == "existential there event":
        return False
    if topic == "existential there with ing":
        return _starts_with_existential_there(sentence_text) and bool(re.search(r"\bthere\s+(?:is|are|was|were)\b.+\b[a-z-]+ing\b", sentence_text))
    if topic == "existential there agreement":
        return _starts_with_existential_there(sentence_text)
    if topic == "existential there with seem or appear":
        return bool(re.match(r"^there\s+(?:seems?|appears?)\b", sentence_text))
    if topic == "existential there with passive reporting verb":
        return bool(re.match(r"^there\s+is\s+(?:said|expected|thought|believed)\s+to\s+be\b", sentence_text))
    if topic == "existential there formal literary":
        return bool(re.match(r"^there\s+(?:remains?|remained|followed|comes|come)\b", sentence_text))
    return False


def _phrase_candidate_compatible(note_row: dict[str, Any], phrase: dict[str, Any]) -> bool:
    projection = note_row.get("template_projection") or {}
    kind = _norm(projection.get("template_kind")).lower()
    phrase_text = _norm(phrase.get("content")).lower()
    phrase_pos = _norm(phrase.get("part_of_speech")).lower()

    if kind.startswith("prepositional_phrase"):
        return phrase_pos == "prepositional phrase"

    if "relative_clause" in kind:
        if not _contains_relative_marker(phrase_text):
            return False
        if "preposition_marker" in kind:
            return _starts_with_preposition_marker(phrase_text)
        return True

    return True


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("note_text"),
        candidate.get("template_kind"),
        candidate.get("source_book"),
        candidate.get("topic"),
        candidate.get("match_level"),
    )


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    match_rank = {"exact": 0, "bucketed": 1, "presence": 2}
    return sorted(
        candidates,
        key=lambda item: (
            match_rank.get(str(item.get("match_level")), 9),
            len(item.get("risk_flags") or []),
            str(item.get("source_book") or ""),
            str(item.get("topic") or ""),
            str(item.get("note_text") or ""),
        ),
    )


def _append_candidates(
    out: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    rows: list[dict[str, Any]],
    *,
    match_level: str,
    compatible,
) -> None:
    for row in rows:
        if not compatible(row):
            continue
        candidate = _note_payload(row, match_level=match_level)
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)


def _build_note_indexes(note_rows_path: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexes = {
        "sentence_exact": defaultdict(list),
        "sentence_bucketed": defaultdict(list),
        "sentence_presence": defaultdict(list),
        "sentence_topic": defaultdict(list),
        "phrase_exact": defaultdict(list),
        "phrase_bucketed": defaultdict(list),
        "phrase_presence": defaultdict(list),
    }
    for row in _iter_jsonl(note_rows_path):
        alignment = row.get("family_alignment") or {}
        context = row.get("context") or {}
        node_type = _norm(context.get("node_type")).lower()
        sentence_alignment = alignment.get("sentence") or {}
        if node_type == "sentence":
            if _source_sentence_note_usable(row):
                topic = _norm(((row.get("source") or {}).get("topic"))).lower()
                indexes["sentence_topic"][topic].append(row)
        if node_type == "phrase":
            phrase_alignment = alignment.get("phrase") or {}
            if phrase_alignment.get("exact_family_id"):
                indexes["phrase_exact"][phrase_alignment["exact_family_id"]].append(row)
            if phrase_alignment.get("bucketed_family_id"):
                indexes["phrase_bucketed"][phrase_alignment["bucketed_family_id"]].append(row)
            if phrase_alignment.get("presence_family_id"):
                indexes["phrase_presence"][phrase_alignment["presence_family_id"]].append(row)
    return indexes


def project_notes_onto_corpus(
    *,
    corpus_input_path: str,
    templated_note_rows_path: str,
    spacy_model: str,
    max_phrase_depth: int,
    max_sentence_candidates: int,
    max_phrase_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    indexes = _build_note_indexes(templated_note_rows_path)
    corpus_rows: list[dict[str, Any]] = []
    report_counts: Counter[str] = Counter()
    note_counts: Counter[str] = Counter()
    source_texts_with_coverage: set[str] = set()

    for source_row in _iter_jsonl(corpus_input_path):
        source_text = _norm(source_row.get("text"))
        if not source_text:
            continue
        profiles = _build_sentence_profiles(source_text, nlp, max_phrase_depth=max_phrase_depth)
        for sent_index, profile in enumerate(profiles):
            report_counts["sentence_nodes_total"] += 1
            sentence_candidates: list[dict[str, Any]] = []
            sentence_seen: set[tuple[Any, ...]] = set()
            for topic, rows in indexes["sentence_topic"].items():
                if not rows:
                    continue
                if not _sentence_candidate_compatible(rows[0], profile):
                    continue
                _append_candidates(
                    sentence_candidates,
                    sentence_seen,
                    rows,
                    match_level="topic",
                    compatible=lambda row, profile=profile: _sentence_candidate_compatible(row, profile),
                )
            sentence_candidates = _sort_candidates(sentence_candidates)[:max_sentence_candidates]
            if sentence_candidates:
                report_counts["sentence_nodes_with_sentence_notes"] += 1
                source_texts_with_coverage.add(source_row.get("id") or source_text)
                note_counts["sentence_note_candidates_total"] += len(sentence_candidates)

            phrase_entries: list[dict[str, Any]] = []
            phrase_covered = False
            for phrase in profile["phrase_entries"]:
                report_counts["phrase_nodes_total"] += 1
                phrase_candidates: list[dict[str, Any]] = []
                phrase_seen: set[tuple[Any, ...]] = set()
                _append_candidates(
                    phrase_candidates,
                    phrase_seen,
                    indexes["phrase_exact"].get(phrase["exact_family_id"], []),
                    match_level="exact",
                    compatible=lambda row, phrase=phrase: _phrase_candidate_compatible(row, phrase),
                )
                _append_candidates(
                    phrase_candidates,
                    phrase_seen,
                    indexes["phrase_bucketed"].get(phrase["bucketed_family_id"], []),
                    match_level="bucketed",
                    compatible=lambda row, phrase=phrase: _phrase_candidate_compatible(row, phrase),
                )
                _append_candidates(
                    phrase_candidates,
                    phrase_seen,
                    indexes["phrase_presence"].get(phrase["presence_family_id"], []),
                    match_level="presence",
                    compatible=lambda row, phrase=phrase: _phrase_candidate_compatible(row, phrase),
                )
                phrase_candidates = _sort_candidates(phrase_candidates)[:max_phrase_candidates]
                if phrase_candidates:
                    report_counts["phrase_nodes_with_notes"] += 1
                    phrase_covered = True
                    source_texts_with_coverage.add(source_row.get("id") or source_text)
                    note_counts["phrase_note_candidates_total"] += len(phrase_candidates)
                phrase_entry = dict(phrase)
                phrase_entry["note_candidates"] = phrase_candidates
                phrase_entries.append(phrase_entry)

            if phrase_covered:
                report_counts["sentence_nodes_with_phrase_notes"] += 1
            if sentence_candidates or phrase_covered:
                report_counts["sentence_nodes_with_any_notes"] += 1

            corpus_rows.append(
                {
                    "projection_version": "book_note_corpus_projection_v1",
                    "source_document": {
                        "id": _norm(source_row.get("id")),
                        "source_name": _norm(source_row.get("source_name")),
                        "source_url": _norm(source_row.get("source_url")),
                    },
                    "sentence_index_in_source": sent_index,
                    "sentence_text": profile["sentence_text"],
                    "source_span": profile["source_span"],
                    "sentence_family_alignment": {
                        "exact_family_id": profile["sentence_exact_family_id"],
                        "bucketed_family_id": profile["sentence_bucketed_family_id"],
                        "presence_family_id": profile["sentence_presence_family_id"],
                    },
                    "sentence_note_candidates": sentence_candidates,
                    "phrase_entries": phrase_entries,
                }
            )

    report = {
        "projection_version": "book_note_corpus_projection_v1",
        "corpus_input_path": str(Path(corpus_input_path).resolve()),
        "templated_note_rows_path": str(Path(templated_note_rows_path).resolve()),
        "spacy_model": spacy_model,
        "max_phrase_depth": max_phrase_depth,
        "max_sentence_candidates": max_sentence_candidates,
        "max_phrase_candidates": max_phrase_candidates,
        "source_documents_total": sum(1 for _ in _iter_jsonl(corpus_input_path)),
        "source_documents_with_any_notes": len(source_texts_with_coverage),
        "sentence_nodes_total": report_counts["sentence_nodes_total"],
        "sentence_nodes_with_sentence_notes": report_counts["sentence_nodes_with_sentence_notes"],
        "sentence_nodes_with_phrase_notes": report_counts["sentence_nodes_with_phrase_notes"],
        "sentence_nodes_with_any_notes": report_counts["sentence_nodes_with_any_notes"],
        "phrase_nodes_total": report_counts["phrase_nodes_total"],
        "phrase_nodes_with_notes": report_counts["phrase_nodes_with_notes"],
        "sentence_note_candidates_total": note_counts["sentence_note_candidates_total"],
        "phrase_note_candidates_total": note_counts["phrase_note_candidates_total"],
        "all_note_candidates_total": note_counts["sentence_note_candidates_total"] + note_counts["phrase_note_candidates_total"],
    }
    return corpus_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Project templated book notes onto the natural ingested corpus.")
    parser.add_argument("--corpus-input", default="data/raw_sources/ingested_sentences.jsonl")
    parser.add_argument("--templated-notes-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--max-phrase-depth", type=int, default=2)
    parser.add_argument("--max-sentence-candidates", type=int, default=3)
    parser.add_argument("--max-phrase-candidates", type=int, default=2)
    args = parser.parse_args()

    rows, report = project_notes_onto_corpus(
        corpus_input_path=args.corpus_input,
        templated_note_rows_path=args.templated_notes_input,
        spacy_model=args.spacy_model,
        max_phrase_depth=args.max_phrase_depth,
        max_sentence_candidates=args.max_sentence_candidates,
        max_phrase_candidates=args.max_phrase_candidates,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
