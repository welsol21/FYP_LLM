"""English synonym providers."""

from __future__ import annotations

from typing import Protocol


class SynonymProvider(Protocol):
    def get_synonyms(self, text: str, pos: str | None, top_k: int) -> list[str]:
        ...


class WordNetSynonymProvider:
    """WordNet-backed synonym provider for English tokens/spans."""

    _WORDNET_POS_MAP = {
        "noun": "n",
        "verb": "v",
        "adjective": "a",
        "adverb": "r",
    }
    _UNSUPPORTED_FUNCTION_POS = {
        "auxiliary verb",
        "modal verb",
        "pronoun",
        "preposition",
        "article",
        "determiner",
        "conjunction",
        "particle",
        "interjection",
        "sentence",
        "verb phrase",
        "noun phrase",
        "prepositional phrase",
    }

    def __init__(self) -> None:
        try:
            from nltk.corpus import wordnet as wn  # type: ignore
        except Exception as exc:  # pragma: no cover - import error path
            raise ImportError("nltk is required for synonyms provider: install with `pip install nltk`") from exc

        try:
            _ = wn.synsets("test")
        except LookupError as exc:  # pragma: no cover - runtime env dependent
            raise LookupError(
                "WordNet data is missing. Run `.venv/bin/python -m nltk.downloader wordnet omw-1.4`."
            ) from exc
        self._wn = wn

    @staticmethod
    def _normalize_candidate(value: str) -> str:
        return " ".join(value.replace("_", " ").strip().split()).lower()

    def get_synonyms(self, text: str, pos: str | None, top_k: int) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        k = max(1, int(top_k))
        normalized_raw = self._normalize_candidate(raw)
        normalized_pos = str(pos or "").strip().lower()
        if normalized_pos in self._UNSUPPORTED_FUNCTION_POS:
            return []
        wn_pos = self._WORDNET_POS_MAP.get(normalized_pos)
        if wn_pos is None and normalized_pos:
            # If POS is explicitly provided but not lexical, skip synonyms to avoid semantic noise.
            return []
        synsets = self._wn.synsets(raw, pos=wn_pos) if wn_pos else self._wn.synsets(raw)

        out: list[str] = []
        seen: set[str] = set()
        for synset in synsets:
            for lemma in synset.lemma_names():
                candidate = self._normalize_candidate(lemma)
                if not candidate or candidate == normalized_raw:
                    continue
                if candidate in seen:
                    continue
                seen.add(candidate)
                out.append(candidate)
                if len(out) >= k:
                    return out
        return out
