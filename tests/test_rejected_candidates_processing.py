import unittest

from ela_pipeline.annotate.rejected_candidates import (
    RejectedCandidateFilterConfig,
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

    def test_sentence_prefix_whitelist_allowed_only_with_flag(self):
        cfg = RejectedCandidateFilterConfig(allow_sentence_prefix_candidates=True)
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
            "Node content. Part of speech",
        )

    def test_deduplicates_by_normalized_form(self):
        rejected, stats = normalize_and_aggregate_rejected_candidates(
            rejected_candidates=[
                "Node content. Part of speech.",
                "Node content. Part of speech",
            ],
            config=RejectedCandidateFilterConfig(
                reject_stop_substrings=[],
                reject_regex_patterns=[],
            ),
        )
        self.assertEqual(rejected, ["Node content. Part of speech"])
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
                reject_stop_substrings=[],
                reject_regex_patterns=[],
            ),
        )
        self.assertEqual(rejected, ["Bad candidate"])
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
                reject_stop_substrings=[],
                reject_regex_patterns=[],
            ),
        )
        self.assertEqual(rejected, [])
        self.assertEqual(stats, [])


if __name__ == "__main__":
    unittest.main()
