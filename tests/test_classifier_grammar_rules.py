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


if __name__ == "__main__":
    unittest.main()
