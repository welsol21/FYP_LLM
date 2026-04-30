import unittest

from scripts.build_paired_template_signature_dataset import (
    _drop_ambiguous_inputs,
    _filter_rows_by_target_mode,
    canonicalize_target_text,
)


class BuildPairedTemplateSignatureDatasetTests(unittest.TestCase):
    def test_canonicalize_target_text_merges_existential_there_variants(self):
        canonical, source = canonicalize_target_text(
            "In existential there constructions, agreement normally follows the noun phrase that comes after be."
        )
        self.assertEqual(
            canonical,
            "In existential {{EXISTENTIAL_THERE}} clauses, the form of {{AUXILIARY}} agrees with the {{NOUN_PHRASE}} that follows it.",
        )
        self.assertEqual(source, "canonical_rule::regex_family")

    def test_filter_rows_by_target_mode_keeps_only_template_targets(self):
        rows = [
            {"input": "{{SUBJECT}} {{AUXILIARY}} {{BASE_VERB}}", "target": "A raw target."},
            {"input": "{{SUBJECT}} {{AUXILIARY}} {{BASE_VERB}}", "target": "A {{SUBJECT}} template target."},
        ]
        kept, report = _filter_rows_by_target_mode(rows, target_mode="template_only")
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["target"], "A {{SUBJECT}} template target.")
        self.assertEqual(report["dropped_raw_targets"], 1)
        self.assertEqual(report["dropped_template_targets"], 0)

    def test_drop_ambiguous_inputs_removes_conflicting_input_groups(self):
        rows = [
            {"input": "{{SUBJECT}} {{AUXILIARY}} {{BASE_VERB}}", "target": "Target A"},
            {"input": "{{SUBJECT}} {{AUXILIARY}} {{BASE_VERB}}", "target": "Target B"},
            {"input": "{{IF_CLAUSE}}, {{WILL_RESULT_CLAUSE}}", "target": "Stable target"},
        ]
        kept, report = _drop_ambiguous_inputs(rows)
        self.assertEqual(kept, [{"input": "{{IF_CLAUSE}}, {{WILL_RESULT_CLAUSE}}", "target": "Stable target"}])
        self.assertEqual(report["ambiguous_input_groups_dropped"], 1)
        self.assertEqual(report["ambiguous_input_rows_dropped"], 2)
        self.assertEqual(report["max_targets_for_dropped_input"], 2)


if __name__ == "__main__":
    unittest.main()
