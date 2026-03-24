import unittest

from ela_pipeline.classifier.grammar_rules import map_pedagogical_grammar_classes


class GrammarRulesTests(unittest.TestCase):
    def test_maps_modal_perfect(self):
        classes = map_pedagogical_grammar_classes(
            mood="modal",
            aspect="perfect",
            tam_construction="modal_perfect",
            dep_labels=["root", "aux"],
            content="She should have left.",
        )
        self.assertIn("modal_perfect", classes)

    def test_maps_present_simple_negative(self):
        classes = map_pedagogical_grammar_classes(
            tense="present",
            tam_construction="present_simple",
            dep_labels=["root", "neg"],
            content="She does not work.",
        )
        self.assertIn("present_simple_negative", classes)

    def test_maps_passive_voice(self):
        classes = map_pedagogical_grammar_classes(
            voice="passive",
            tam_construction="passive_voice",
            dep_labels=["root", "aux:pass", "nsubj:pass"],
            content="The work was finished.",
        )
        self.assertIn("passive_voice", classes)

    def test_maps_past_continuous_not_present_continuous(self):
        # "past progressive" short_tense must produce past_continuous, not present_continuous
        classes = map_pedagogical_grammar_classes(
            tense="past progressive",
            aspect="progressive",
            content="She was brushing the mantel.",
        )
        self.assertIn("past_continuous", classes)
        self.assertNotIn("present_continuous", classes)

    def test_maps_present_continuous(self):
        # pure progressive aspect without "past" must still produce present_continuous
        classes = map_pedagogical_grammar_classes(
            tense="progressive",
            aspect="progressive",
            content="She is reading.",
        )
        self.assertIn("present_continuous", classes)
        self.assertNotIn("past_continuous", classes)

    def test_past_simple_not_confused_with_progressive(self):
        # plain past tense must still produce past_simple_affirmative
        classes = map_pedagogical_grammar_classes(
            tense="past",
            aspect="simple",
            content="She left.",
        )
        self.assertIn("past_simple_affirmative", classes)
        self.assertNotIn("past_continuous", classes)
        self.assertNotIn("present_continuous", classes)


if __name__ == "__main__":
    unittest.main()
