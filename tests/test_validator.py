import json
import unittest

from ela_pipeline.validation.validator import validate_contract, validate_frozen_structure


class ValidatorTests(unittest.TestCase):
    @staticmethod
    def _normalize_strict_tam_nulls(node):
        for field in ("tense", "aspect", "mood", "voice", "finiteness"):
            if node.get(field) == "null":
                node[field] = None
        for child in node.get("linguistic_elements", []):
            ValidatorTests._normalize_strict_tam_nulls(child)

    @staticmethod
    def _normalize_strict_feature_nulls(node):
        features = node.get("features")
        if isinstance(features, dict):
            for key, value in list(features.items()):
                if value == "null":
                    features[key] = None
        for child in node.get("linguistic_elements", []):
            ValidatorTests._normalize_strict_feature_nulls(child)

    @staticmethod
    def _inject_minimal_v2_fields(node, parent_id, next_id):
        node["node_id"] = f"n{next_id[0]}"
        next_id[0] += 1
        node["parent_id"] = parent_id
        node["source_span"] = {"start": 0, "end": len(node.get("content", ""))}
        node["grammatical_role"] = "unknown"
        node["schema_version"] = "v2"
        for child in node.get("linguistic_elements", []):
            ValidatorTests._inject_minimal_v2_fields(child, node["node_id"], next_id)

    def test_sample_contract_valid(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_frozen_detects_content_change(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            skeleton = json.load(f)

        enriched = json.loads(json.dumps(skeleton))
        key = next(iter(enriched))
        enriched[key]["linguistic_elements"][0]["content"] = "BROKEN"

        result = validate_frozen_structure(skeleton, enriched)
        self.assertFalse(result.ok)

    def test_rejects_one_word_phrase(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["linguistic_elements"][0]["linguistic_elements"] = [
            sentence["linguistic_elements"][0]["linguistic_elements"][0]
        ]

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("at least 2 Word nodes" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_source_span(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["source_span"] = {"start": 10, "end": 2}
        sentence["node_id"] = "n1"
        sentence["parent_id"] = None

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("source_span.end" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_grammatical_role(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["grammatical_role"] = {"label": "clause"}

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("grammatical_role" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_dependency_fields(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        word["node_id"] = "n100"
        word["parent_id"] = "p1"
        word["dep_label"] = {"bad": "value"}
        word["head_id"] = "n100"

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("dep_label" in err.path or "head_id" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_verbal_fields(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["aspect"] = 1

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("aspect" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_tam_construction(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["tam_construction"] = {"bad": "value"}

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("tam_construction" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_arbitrary_tam_construction_value(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["tam_construction"] = "perfect_modal"

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_invalid_optional_features(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        word["features"] = {"number": 1}

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("features.number" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_valid_optional_typed_notes(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["notes"] = [
            {
                "text": "This sentence has a finite predicate.",
                "kind": "syntactic",
                "confidence": 0.9,
                "source": "model",
            }
        ]

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_invalid_optional_typed_notes(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["notes"] = [
            {
                "text": 123,
                "kind": "syntax",
                "confidence": 1.5,
                "source": "llm",
            }
        ]

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".notes[0]." in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_valid_optional_trace_fields(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["quality_flags"] = ["note_generated", "model_used"]
        sentence["rejected_candidates"] = ["Bad template output"]
        sentence["reason_codes"] = ["MODEL_NOTE_ACCEPTED"]

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_accepts_valid_optional_rejected_candidate_stats(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["rejected_candidate_stats"] = [
            {
                "text": "Template-like output",
                "count": 3,
                "reasons": ["MODEL_OUTPUT_LOW_QUALITY", "MODEL_NOTE_UNSUITABLE"],
            }
        ]

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_invalid_optional_trace_fields(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["quality_flags"] = "model_used"
        sentence["rejected_candidates"] = [123]
        sentence["reason_codes"] = [None]

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".quality_flags" in err.path or ".rejected_candidates" in err.path or ".reason_codes" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_invalid_optional_rejected_candidate_stats(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["rejected_candidate_stats"] = [
            {
                "text": "Bad item",
                "count": 0,
                "reasons": [123],
            }
        ]

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".rejected_candidate_stats" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_valid_optional_schema_version(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["schema_version"] = "v2"

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_invalid_optional_schema_version(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["schema_version"] = ""

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".schema_version" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_missing_core_fields_in_v2_strict(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        result = validate_contract(data, validation_mode="v2_strict")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("Missing required fields" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_v2_strict_when_core_fields_present(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        self._inject_minimal_v2_fields(sentence, None, [1])
        self._normalize_strict_tam_nulls(sentence)
        self._normalize_strict_feature_nulls(sentence)

        result = validate_contract(data, validation_mode="v2_strict")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_string_null_tam_values_in_v2_strict(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        self._inject_minimal_v2_fields(sentence, None, [1])
        sentence["tense"] = "null"

        result = validate_contract(data, validation_mode="v2_strict")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("must use real null" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_inconsistent_modal_perfect_policy_in_v2_strict(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        self._inject_minimal_v2_fields(sentence, None, [1])
        self._normalize_strict_tam_nulls(sentence)
        sentence["tam_construction"] = "modal_perfect"
        sentence["mood"] = "modal"
        sentence["aspect"] = "perfect"
        sentence["tense"] = "past"

        result = validate_contract(data, validation_mode="v2_strict")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("modal_perfect requires tense=null" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_string_null_feature_values_in_v2_strict(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        self._inject_minimal_v2_fields(sentence, None, [1])
        self._normalize_strict_tam_nulls(sentence)
        sentence["linguistic_elements"][0]["linguistic_elements"][0]["features"] = {
            "number": "null",
            "verb_form": "fin",
        }

        result = validate_contract(data, validation_mode="v2_strict")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("feature values must use real null" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_real_null_feature_values_in_v2_strict(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        self._inject_minimal_v2_fields(sentence, None, [1])
        self._normalize_strict_tam_nulls(sentence)
        sentence["linguistic_elements"][0]["linguistic_elements"][0]["features"] = {
            "number": None,
            "verb_form": "fin",
        }

        result = validate_contract(data, validation_mode="v2_strict")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_real_null_tam_values_in_v1(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["tense"] = None

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".tense" in err.path for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_tam_dropped_for_tam_relevant_node(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["template_selection"] = {
            "level": "L2_DROP_TAM",
            "template_id": "SENTENCE_FINITE_CLAUSE",
            "matched_level_reason": "tam_dropped",
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_tam_dropped_for_non_tam_relevant_node(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        word = sentence["linguistic_elements"][0]["linguistic_elements"][0]
        word["type"] = "Word"
        word["part_of_speech"] = "noun"
        word["tam_construction"] = "none"
        word["template_selection"] = {
            "level": "L2_DROP_TAM",
            "template_id": "WORD_NOUN_COMMON",
            "matched_level_reason": "tam_dropped",
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("only allowed for TAM-relevant nodes" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_missing_backoff_used_for_non_l1_level(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["quality_flags"] = ["template_selected", "rule_used"]
        sentence["template_selection"] = {
            "level": "L2_DROP_TAM",
            "template_id": "SENTENCE_FINITE_CLAUSE",
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("backoff_used is required" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_rejects_backoff_used_for_l1_exact(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["quality_flags"] = ["template_selected", "rule_used", "backoff_used"]
        sentence["template_selection"] = {
            "level": "L1_EXACT",
            "template_id": "SENTENCE_FINITE_CLAUSE",
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any("backoff_used is not allowed" in err.message for err in result.errors),
            msg=str(result.errors),
        )

    def test_accepts_valid_optional_backoff_summary(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["backoff_nodes_count"] = 2
        sentence["backoff_summary"] = {
            "nodes": ["n1", "n2"],
            "reasons": ["tam_dropped"],
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_rejects_invalid_optional_backoff_summary(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["backoff_nodes_count"] = "2"
        sentence["backoff_summary"] = {
            "nodes": [1],
            "reasons": [None],
        }

        result = validate_contract(data, validation_mode="v1")
        self.assertFalse(result.ok)
        self.assertTrue(
            any(".backoff_nodes_count" in err.path or ".backoff_summary" in err.path for err in result.errors),
            msg=str(result.errors),
        )


if __name__ == "__main__":
    unittest.main()
