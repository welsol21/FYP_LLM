"""MASC CoNLL ingest for validation/control corpus slices."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from zipfile import ZipFile


def _iter_masc_members(zf: ZipFile) -> list[str]:
    return sorted(
        name
        for name in zf.namelist()
        if name.endswith(".conll")
        and name.startswith("masc-conll/data/")
        and "/__MACOSX/" not in name
        and not PurePosixPath(name).name.startswith("._")
    )


def _surface_form(parts: list[str]) -> str:
    form = parts[1].strip() if len(parts) > 1 else ""
    if form and form != "_":
        return form
    return ""


def _join_tokens(tokens: list[str]) -> str:
    no_space_before = {".", ",", "!", "?", ":", ";", "%", ")", "]", "}", "'s", "n't", "''", '"'}
    no_space_after = {"(", "[", "{", "``", '"'}
    out = ""
    for token in tokens:
        piece = token.strip()
        if not piece or piece == "_":
            continue
        if piece in {"-lrb-"}:
            piece = "("
        elif piece in {"-rrb-"}:
            piece = ")"
        if not out:
            out = piece
            continue
        if piece in no_space_before or out.endswith(tuple(no_space_after)):
            out += piece
        elif piece == "-" or out.endswith("-"):
            out += piece
        else:
            out += f" {piece}"
    return out.strip()


def load_masc_conll_sentences(
    zip_path: str,
    *,
    member_paths: list[str] | None = None,
    limit_files: int | None = None,
    min_chars: int = 20,
    max_chars: int = 400,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ZipFile(zip_path) as zf:
        selected_members = member_paths if member_paths is not None else _iter_masc_members(zf)
        if limit_files is not None:
            selected_members = selected_members[:limit_files]

        for member_path in selected_members:
            genre = PurePosixPath(member_path).parts[2] if len(PurePosixPath(member_path).parts) > 2 else "unknown"
            sentence_tokens: list[str] = []
            sentence_index = 0
            content = zf.read(member_path).decode("utf-8", errors="ignore")
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line:
                    text = _join_tokens(sentence_tokens)
                    if min_chars <= len(text) <= max_chars:
                        rows.append(
                            {
                                "text": text,
                                "provenance": {
                                    "source": "MASC",
                                    "member_path": member_path,
                                    "genre_bucket": genre,
                                    "sentence_index_in_file": sentence_index,
                                    "sentence_boundary_source": "masc_conll_blankline",
                                },
                            }
                        )
                    sentence_tokens = []
                    sentence_index += 1
                    continue

                parts = raw_line.split("\t")
                if len(parts) < 10:
                    continue
                surface = _surface_form(parts)
                if surface:
                    sentence_tokens.append(surface)

            if sentence_tokens:
                text = _join_tokens(sentence_tokens)
                if min_chars <= len(text) <= max_chars:
                    rows.append(
                        {
                            "text": text,
                            "provenance": {
                                "source": "MASC",
                                "member_path": member_path,
                                "genre_bucket": genre,
                                "sentence_index_in_file": sentence_index,
                                "sentence_boundary_source": "masc_conll_blankline",
                            },
                        }
                    )
    return rows
