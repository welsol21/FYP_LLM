"""spaCy loading and parsing utilities."""

from __future__ import annotations

import spacy


def load_nlp(model_name: str = "en_core_web_sm"):
    nlp = spacy.load(model_name)
    if "parser" not in nlp.pipe_names and "senter" not in nlp.pipe_names:
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
    return nlp
