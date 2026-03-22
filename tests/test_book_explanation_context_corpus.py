import unittest

from ela_pipeline.dataset.build_book_explanation_context_corpus import (
    build_note_context_contract_rows,
    build_note_context_rows,
)


class BookExplanationContextCorpusTests(unittest.TestCase):
    def test_build_note_context_rows_extracts_explanation_and_explicit_context(self):
        snippet_rows = [
            {
                "source_path": "/tmp/book.pdf",
                "parser_name": "pdf",
                "format": "pdf",
                "topic_key": "question_tags",
                "anchor": "question tags",
                "heading": "Question tags",
                "snippet_text": (
                    "Question tags are short questions added at the end of a statement. "
                    'For example: "You are ready, aren\'t you?"'
                ),
            }
        ]

        rows, report = build_note_context_rows(snippet_rows)
        self.assertGreaterEqual(report["pairs_built"], 1)
        self.assertEqual(rows[0]["pair_method"], "explicit_context")
        self.assertIn("Question tags are short questions", rows[0]["explanation_text"])
        self.assertIn("You are ready", rows[0]["context_text"])

    def test_build_note_context_contract_rows_attaches_book_templated_phrase_note(self):
        note_context_rows = [
            {
                "row_id": "row_1",
                "source_path": "/tmp/book.pdf",
                "parser_name": "pdf",
                "format": "pdf",
                "topic_key": "prepositional phrase",
                "heading": "Prepositional phrases",
                "explanation_text": "A prepositional phrase can add location information.",
                "context_text": "He waited at the station.",
                "pair_method": "explicit_context",
                "risk_flags": [],
                "book_template_id_sentence": "",
                "book_template_id_phrase": "PHRASE_PP_GENERAL",
            }
        ]

        rows, report = build_note_context_contract_rows(note_context_rows)
        self.assertEqual(report["contracts_built"], 1)
        self.assertGreaterEqual(report["matched_phrase_nodes"], 1)
        contract = rows[0]["context_contract"]

        def walk(node):
            yield node
            for child in node.get("linguistic_elements") or []:
                if isinstance(child, dict):
                    yield from walk(child)

        found = False
        for sentence_node in contract.values():
            for node in walk(sentence_node):
                if node.get("book_templated_notes"):
                    found = True
                    self.assertEqual(node["book_templated_notes"][0]["book_template_id"], "PHRASE_PP_GENERAL")
                    break
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
