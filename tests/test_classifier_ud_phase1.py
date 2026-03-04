import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.ud_phase1 import (
    extract_phase1_grammar_signal,
    load_ud_conllu,
    validate_phase1_dataset_gates,
)


class UDPhase1Tests(unittest.TestCase):
    def test_load_ud_conllu_extracts_sentence_tokens_and_provenance(self):
        sample = textwrap.dedent(
            """
            # newdoc id = GUM_academic_art
            # meta::genre = academic
            # sent_id = ewt-train-1
            # text = She walks home.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t2\tnsubj\t_\t_
            2\twalks\twalk\tVERB\tVBZ\tMood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin\t0\troot\t_\t_
            3\thome\thome\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "en_ewt-ud-train.conllu"
            path.write_text(sample + "\n", encoding="utf-8")

            rows = load_ud_conllu(
                input_path=str(path),
                treebank="UD_English-EWT",
                split="train",
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["text"], "She walks home.")
        self.assertEqual(row["provenance"]["treebank"], "UD_English-EWT")
        self.assertEqual(row["provenance"]["split"], "train")
        self.assertEqual(row["provenance"]["sent_id"], "ewt-train-1")
        self.assertEqual(row["provenance"]["doc_id"], "GUM_academic_art")
        self.assertEqual(row["provenance"]["genre"], "academic")
        self.assertEqual(len(row["tokens"]), 4)
        self.assertEqual(row["tokens"][1]["lemma"], "walk")
        self.assertEqual(row["tokens"][1]["dep"], "root")
        self.assertEqual(row["tokens"][1]["morph"]["Tense"], "Pres")

    def test_load_ud_conllu_propagates_doc_level_genre_to_following_sentences(self):
        sample = textwrap.dedent(
            """
            # newdoc id = GUM_academic_demo
            # meta::genre = academic
            # sent_id = gum-1
            # text = She walks home.
            1\tShe\tshe\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t2\tnsubj\t_\t_
            2\twalks\twalk\tVERB\tVBZ\tMood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin\t0\troot\t_\t_
            3\thome\thome\tADV\tRB\t_\t2\tadvmod\t_\tSpaceAfter=No
            4\t.\t.\tPUNCT\t.\t_\t2\tpunct\t_\t_

            # sent_id = gum-2
            # text = It was written carefully.
            1\tIt\tit\tPRON\tPRP\tCase=Nom|Number=Sing|Person=3\t3\tnsubj:pass\t_\t_
            2\twas\tbe\tAUX\tVBD\tTense=Past|VerbForm=Fin\t3\taux:pass\t_\t_
            3\twritten\twrite\tVERB\tVBN\tVerbForm=Part\t0\troot\t_\t_
            4\tcarefully\tcarefully\tADV\tRB\t_\t3\tadvmod\t_\tSpaceAfter=No
            5\t.\t.\tPUNCT\t.\t_\t3\tpunct\t_\t_
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "en_gum-ud-train.conllu"
            path.write_text(sample + "\n", encoding="utf-8")
            rows = load_ud_conllu(
                input_path=str(path),
                treebank="UD_English-GUM",
                split="train",
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["provenance"]["genre"], "academic")
        self.assertEqual(rows[1]["provenance"]["genre"], "academic")
        self.assertEqual(rows[1]["provenance"]["doc_id"], "GUM_academic_demo")

    def test_validate_phase1_dataset_gates_rejects_cross_level_ambiguity(self):
        rows = [
            {
                "text": "She walks home.",
                "cefr_level": "A1",
                "grammar_classes": ["present_simple_affirmative"],
                "grammar_evidence": {"dep_signature": ["nsubj", "root"]},
                "note_blueprints": {"elementary": "A1 note", "intermediate": "A2 note", "advanced": "B1 note"},
            },
            {
                "text": "They walk home.",
                "cefr_level": "A2",
                "grammar_classes": ["present_simple_affirmative"],
                "grammar_evidence": {"dep_signature": ["nsubj", "root"]},
                "note_blueprints": {"elementary": "A1 note", "intermediate": "A2 note", "advanced": "B1 note"},
            },
        ]

        report = validate_phase1_dataset_gates(rows, max_ambiguous_grammar_combo_ratio=0.0)
        self.assertFalse(report["passed"])
        self.assertIn("grammar_combo_ambiguity", report["failed_gates"])

    def test_validate_phase1_dataset_gates_rejects_missing_evidence_and_blueprints(self):
        rows = [
            {
                "text": "She walks home.",
                "cefr_level": "A1",
                "grammar_classes": ["present_simple_affirmative"],
                "grammar_evidence": {},
                "note_blueprints": {"elementary": "", "intermediate": "A2 note", "advanced": "B1 note"},
            }
        ]

        report = validate_phase1_dataset_gates(rows)
        self.assertFalse(report["passed"])
        self.assertIn("evidence_completeness", report["failed_gates"])
        self.assertIn("blueprint_completeness", report["failed_gates"])

    def test_extract_phase1_grammar_signal_detects_present_simple_affirmative(self):
        row = {
            "text": "She walks home.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {"Person": "3"}, "head": 2, "dep": "nsubj"},
                {
                    "id": 2,
                    "text": "walks",
                    "lemma": "walk",
                    "upos": "VERB",
                    "xpos": "VBZ",
                    "morph": {"Tense": "Pres", "VerbForm": "Fin", "Number": "Sing", "Person": "3"},
                    "head": 0,
                    "dep": "root",
                },
                {"id": 3, "text": "home", "lemma": "home", "upos": "ADV", "xpos": "RB", "morph": {}, "head": 2, "dep": "advmod"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("present_simple_affirmative", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "present_simple")
        self.assertEqual(signal["finite_root"]["lemma"], "walk")

    def test_extract_phase1_grammar_signal_detects_past_simple_affirmative(self):
        row = {
            "text": "She walked home.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {"Person": "3"}, "head": 2, "dep": "nsubj"},
                {
                    "id": 2,
                    "text": "walked",
                    "lemma": "walk",
                    "upos": "VERB",
                    "xpos": "VBD",
                    "morph": {"Tense": "Past", "VerbForm": "Fin"},
                    "head": 0,
                    "dep": "root",
                },
                {"id": 3, "text": "home", "lemma": "home", "upos": "ADV", "xpos": "RB", "morph": {}, "head": 2, "dep": "advmod"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("past_simple_affirmative", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "past_simple")

    def test_extract_phase1_grammar_signal_detects_present_simple_question(self):
        row = {
            "text": "Do you like tea?",
            "tokens": [
                {"id": 1, "text": "Do", "lemma": "do", "upos": "AUX", "xpos": "VBP", "morph": {"Tense": "Pres", "VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 2, "text": "you", "lemma": "you", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 3, "text": "like", "lemma": "like", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 0, "dep": "root"},
                {"id": 4, "text": "tea", "lemma": "tea", "upos": "NOUN", "xpos": "NN", "morph": {}, "head": 3, "dep": "obj"},
                {"id": 5, "text": "?", "lemma": "?", "upos": "PUNCT", "xpos": ".", "morph": {}, "head": 3, "dep": "punct"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("present_simple_question", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "present_simple")

    def test_extract_phase1_grammar_signal_detects_future_will(self):
        row = {
            "text": "She will travel tomorrow.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 2, "text": "will", "lemma": "will", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 3, "text": "travel", "lemma": "travel", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 0, "dep": "root"},
                {"id": 4, "text": "tomorrow", "lemma": "tomorrow", "upos": "ADV", "xpos": "RB", "morph": {}, "head": 3, "dep": "advmod"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("future_will", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "future_will")

    def test_extract_phase1_grammar_signal_detects_going_to_future(self):
        row = {
            "text": "She is going to travel.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 2, "text": "is", "lemma": "be", "upos": "AUX", "xpos": "VBZ", "morph": {"Tense": "Pres", "VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 3, "text": "going", "lemma": "go", "upos": "VERB", "xpos": "VBG", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
                {"id": 4, "text": "to", "lemma": "to", "upos": "PART", "xpos": "TO", "morph": {}, "head": 5, "dep": "mark"},
                {"id": 5, "text": "travel", "lemma": "travel", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 3, "dep": "xcomp"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("future_going_to", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "future_going_to")

    def test_extract_phase1_grammar_signal_detects_modal_can_ability(self):
        row = {
            "text": "She can swim.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 2, "text": "can", "lemma": "can", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 3, "text": "swim", "lemma": "swim", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 0, "dep": "root"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("modal_can_ability", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "modal_can")

    def test_extract_phase1_grammar_signal_detects_modal_should_advice(self):
        row = {
            "text": "You should rest.",
            "tokens": [
                {"id": 1, "text": "You", "lemma": "you", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 2, "text": "should", "lemma": "should", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 3, "text": "rest", "lemma": "rest", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 0, "dep": "root"},
            ],
        }

        signal = extract_phase1_grammar_signal(row)
        self.assertIn("modal_should_advice", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "modal_should")

    def test_extract_phase1_grammar_signal_detects_past_perfect(self):
        row = {
            "text": "She had finished the work.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 3, "dep": "nsubj"},
                {"id": 2, "text": "had", "lemma": "have", "upos": "AUX", "xpos": "VBD", "morph": {"Tense": "Past", "VerbForm": "Fin"}, "head": 3, "dep": "aux"},
                {"id": 3, "text": "finished", "lemma": "finish", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("past_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "past_perfect")

    def test_extract_phase1_grammar_signal_detects_passive_voice(self):
        row = {
            "text": "The letter was written yesterday.",
            "tokens": [
                {"id": 1, "text": "The", "lemma": "the", "upos": "DET", "xpos": "DT", "morph": {}, "head": 2, "dep": "det"},
                {"id": 2, "text": "letter", "lemma": "letter", "upos": "NOUN", "xpos": "NN", "morph": {}, "head": 4, "dep": "nsubj:pass"},
                {"id": 3, "text": "was", "lemma": "be", "upos": "AUX", "xpos": "VBD", "morph": {"Tense": "Past", "VerbForm": "Fin"}, "head": 4, "dep": "aux:pass"},
                {"id": 4, "text": "written", "lemma": "write", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("passive_voice", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "passive_voice")

    def test_extract_phase1_grammar_signal_detects_modal_perfect(self):
        row = {
            "text": "She should have left earlier.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 4, "dep": "nsubj"},
                {"id": 2, "text": "should", "lemma": "should", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 4, "dep": "aux"},
                {"id": 3, "text": "have", "lemma": "have", "upos": "AUX", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 4, "dep": "aux"},
                {"id": 4, "text": "left", "lemma": "leave", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("modal_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "modal_perfect")

    def test_extract_phase1_grammar_signal_detects_non_should_modal_perfect(self):
        row = {
            "text": "She might have left earlier.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 4, "dep": "nsubj"},
                {"id": 2, "text": "might", "lemma": "might", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 4, "dep": "aux"},
                {"id": 3, "text": "have", "lemma": "have", "upos": "AUX", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 4, "dep": "aux"},
                {"id": 4, "text": "left", "lemma": "leave", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("modal_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "modal_perfect")

    def test_extract_phase1_grammar_signal_detects_future_perfect(self):
        row = {
            "text": "She will have finished by noon.",
            "tokens": [
                {"id": 1, "text": "She", "lemma": "she", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 4, "dep": "nsubj"},
                {"id": 2, "text": "will", "lemma": "will", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 4, "dep": "aux"},
                {"id": 3, "text": "have", "lemma": "have", "upos": "AUX", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 4, "dep": "aux"},
                {"id": 4, "text": "finished", "lemma": "finish", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("future_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "future_perfect")

    def test_extract_phase1_grammar_signal_detects_embedded_future_perfect(self):
        row = {
            "text": "They know where to look for it when it shall have ascended again.",
            "tokens": [
                {"id": 1, "text": "They", "lemma": "they", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 2, "dep": "nsubj"},
                {"id": 2, "text": "know", "lemma": "know", "upos": "VERB", "xpos": "VBP", "morph": {"Tense": "Pres", "VerbForm": "Fin"}, "head": 0, "dep": "root"},
                {"id": 3, "text": "where", "lemma": "where", "upos": "SCONJ", "xpos": "WRB", "morph": {}, "head": 5, "dep": "advmod"},
                {"id": 4, "text": "to", "lemma": "to", "upos": "PART", "xpos": "TO", "morph": {}, "head": 5, "dep": "aux"},
                {"id": 5, "text": "look", "lemma": "look", "upos": "VERB", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 2, "dep": "xcomp"},
                {"id": 6, "text": "for", "lemma": "for", "upos": "ADP", "xpos": "IN", "morph": {}, "head": 5, "dep": "prep"},
                {"id": 7, "text": "it", "lemma": "it", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 6, "dep": "pobj"},
                {"id": 8, "text": "when", "lemma": "when", "upos": "SCONJ", "xpos": "WRB", "morph": {}, "head": 12, "dep": "advmod"},
                {"id": 9, "text": "it", "lemma": "it", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 12, "dep": "nsubj"},
                {"id": 10, "text": "shall", "lemma": "shall", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 12, "dep": "aux"},
                {"id": 11, "text": "have", "lemma": "have", "upos": "AUX", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 12, "dep": "aux"},
                {"id": 12, "text": "ascended", "lemma": "ascend", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 5, "dep": "advcl"},
                {"id": 13, "text": "again", "lemma": "again", "upos": "ADV", "xpos": "RB", "morph": {}, "head": 12, "dep": "advmod"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("future_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "future_perfect")

    def test_extract_phase1_grammar_signal_detects_shall_future_perfect(self):
        row = {
            "text": "It shall have been completed by then.",
            "tokens": [
                {"id": 1, "text": "It", "lemma": "it", "upos": "PRON", "xpos": "PRP", "morph": {}, "head": 5, "dep": "nsubj"},
                {"id": 2, "text": "shall", "lemma": "shall", "upos": "AUX", "xpos": "MD", "morph": {"VerbForm": "Fin"}, "head": 5, "dep": "aux"},
                {"id": 3, "text": "have", "lemma": "have", "upos": "AUX", "xpos": "VB", "morph": {"VerbForm": "Inf"}, "head": 5, "dep": "aux"},
                {"id": 4, "text": "been", "lemma": "be", "upos": "AUX", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 5, "dep": "aux"},
                {"id": 5, "text": "completed", "lemma": "complete", "upos": "VERB", "xpos": "VBN", "morph": {"VerbForm": "Part"}, "head": 0, "dep": "root"},
            ],
        }
        signal = extract_phase1_grammar_signal(row)
        self.assertIn("future_perfect", signal["grammar_classes"])
        self.assertEqual(signal["tam_profile"], "future_perfect")


if __name__ == "__main__":
    unittest.main()
