import unittest

from ela_pipeline.annotate.rejected_candidates import (
    RejectedCandidateFilterConfig,
    norm_key,
    normalize_and_aggregate_rejected_candidates,
    normalize_candidate_text,
)


class RejectedCandidatesProcessingTests(unittest.TestCase):
    def test_filters_stop_substring_sensibilisation(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=["Sensibilisation: have faith in her instincts before making the decision."]
        )
        self.assertEqual(rejected, [])
        self.assertEqual(stats, [])

    def test_filters_sentence_prefix_by_default(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=["Sentence: She should have trusted her instincts."]
        )
        self.assertEqual(rejected, [])
        self.assertEqual(stats, [])

    def test_keeps_sentence_prefix_without_colon_in_v3(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=["Sentence should have trusted her instincts before making the decision."]
        )
        self.assertEqual(rejected, [])
        self.assertEqual(stats, [])

    def test_filters_sentence_is_was_in_patterns(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=[
                "Sentence is a noun used as the subject of the clause.",
                "Sentence in her instincts before making the decision.",
                "Sentence was a given to instincts before making the decision.",
            ]
        )
        self.assertEqual(rejected, [])
        self.assertEqual(stats, [])

    def test_sentence_prefix_whitelist_allowed_only_with_flag(self):
        cfg = RejectedCandidateFilterConfig(
            allowlist_sentence_templates=[norm_key("Sentence: {sentence}")]
        )
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=["Sentence: {sentence}"],
            config=cfg,
        )
        self.assertEqual(rejected, ["Sentence: {sentence}"])
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["count"], 1)

    def test_normalization_tail_punctuation_and_spaces(self):
        self.assertEqual(
            normalize_candidate_text("  Node content. Part of speech...   "),
            "Node content. Part of speech.",
        )

    def test_deduplicates_by_normalized_form(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=[
                "Node content. Part of speech.",
                "Node content. Part of speech",
            ],
            config=RejectedCandidateFilterConfig(
                stop_list=[],
            ),
        )
        self.assertEqual(rejected, ["Node content. Part of speech."])
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["count"], 2)

    def test_aggregates_stats_count_and_reasons(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_items=[
                {"text": "Bad candidate.", "reason": "MODEL_OUTPUT_LOW_QUALITY"},
                {"text": "Bad candidate", "reason": "MODEL_NOTE_UNSUITABLE"},
                {"text": "Bad candidate", "reason": "MODEL_OUTPUT_LOW_QUALITY"},
            ],
            config=RejectedCandidateFilterConfig(
                stop_list=[],
            ),
        )
        self.assertEqual(rejected, ["Bad candidate."])
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["count"], 3)
        self.assertEqual(
            stats[0]["reasons"],
            ["MODEL_NOTE_UNSUITABLE", "MODEL_OUTPUT_LOW_QUALITY"],
        )

    def test_filters_length_and_nonalpha_ratio(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=["abc", "a$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%"],
            config=RejectedCandidateFilterConfig(
                stop_list=[],
            ),
        )
        self.assertEqual(rejected, ["a$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%$%"])
        self.assertEqual(len(stats), 1)

    def test_filters_extended_stop_words(self):
        rejected, _ = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=[
                "Persona says this is valid.",
                "Node type or phrase expressing what happens to or about the subject.",
                "Node content. Part of speech.",
                "Sensational use of her instincts before deciding to make the decision.",
                "This candidate does not use proper grammar.",
                "You must use this pattern.",
            ]
        )
        self.assertEqual(rejected, [])

    def test_is_deterministic(self):
        data = [
            "Node content. Part of speech.",
            "Node content. Part of speech",
            "Bad candidate.",
            "Bad candidate",
        ]
        cfg = RejectedCandidateFilterConfig(stop_list=[])
        r1, s1 = normalize_and_aggregate_rejected_candidates(rejected_candidates=data, config=cfg)
        r2, s2 = normalize_and_aggregate_rejected_candidates(rejected_candidates=data, config=cfg)
        self.assertEqual(r1, r2)
        self.assertEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
