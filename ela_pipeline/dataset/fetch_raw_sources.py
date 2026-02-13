"""Fetch raw sentence sources for ingestion pipeline.

Sources implemented:
- UD English EWT (from official UD GitHub .conllu files)
- Tatoeba-derived sentence pairs (ManyThings, CC-BY attribution)
- English Wikinews RSS
"""

from __future__ import annotations

import argparse
import bz2
import json
import re
from pathlib import Path
from typing import Iterable, List

import requests


UD_URLS = [
    "https://raw.githubusercontent.com/UniversalDependencies/UD_English-EWT/master/en_ewt-ud-train.conllu",
    "https://raw.githubusercontent.com/UniversalDependencies/UD_English-EWT/master/en_ewt-ud-dev.conllu",
    "https://raw.githubusercontent.com/UniversalDependencies/UD_English-EWT/master/en_ewt-ud-test.conllu",
]

TATOEBA_ENG_TSV_BZ2 = "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2"
WIKINEWS_RSS_URLS = [
    "https://en.wikinews.org/wiki/Special:NewsFeed?feed=rss",
    "https://en.wikinews.org/w/index.php?title=Special:NewsFeed&feed=rss&count=200",
]


def _norm_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _looks_sentence(s: str) -> bool:
    s = s.strip()
    if len(s) < 8 or len(s) > 260:
        return False
    alpha = sum(ch.isalpha() for ch in s)
    return alpha >= 4


def _fetch_text(url: str, timeout: int = 60) -> str:
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "ELA-DatasetBuilder/1.0 (+https://example.local; research use)",
            "Accept": "text/xml,application/xml,text/plain,*/*",
        },
    )
    r.raise_for_status()
    return r.text


def _extract_ud_sentences(limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for url in UD_URLS:
        text = _fetch_text(url)
        for line in text.splitlines():
            if line.startswith("# text = "):
                sent = _norm_text(line[len("# text = ") :])
                key = sent.lower()
                if key in seen or not _looks_sentence(sent):
                    continue
                out.append(sent)
                seen.add(key)
                if len(out) >= limit:
                    return out
    return out


def _extract_tatoeba_mthings_sentences(limit: int) -> List[str]:
    r = requests.get(TATOEBA_ENG_TSV_BZ2, timeout=180)
    r.raise_for_status()
    raw = bz2.decompress(r.content).decode("utf-8", errors="ignore")
    out: List[str] = []
    seen = set()
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        # Tatoeba format: sentence_id<TAB>lang<TAB>text
        if len(parts) < 3:
            continue
        if parts[1] != "eng":
            continue
        eng = _norm_text(parts[2])
        key = eng.lower()
        if key in seen or not _looks_sentence(eng):
            continue
        out.append(eng)
        seen.add(key)
        if len(out) >= limit:
            break
    return out


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z]+;", " ", s)
    return _norm_text(s)


def _split_sentences(text: str) -> Iterable[str]:
    for part in re.split(r"(?<=[.!?])\s+", text):
        sent = _norm_text(part)
        if _looks_sentence(sent):
            yield sent


def _extract_wikinews_sentences(limit: int) -> List[str]:
    rss = ""
    for url in WIKINEWS_RSS_URLS:
        try:
            rss = _fetch_text(url)
            if rss:
                break
        except Exception:
            continue
    if not rss:
        return []
    # simple RSS extraction
    chunks = re.findall(r"<description>(.*?)</description>", rss, flags=re.DOTALL | re.IGNORECASE)
    out: List[str] = []
    seen = set()
    for chunk in chunks:
        plain = _strip_html(chunk)
        for sent in _split_sentences(plain):
            key = sent.lower()
            if key in seen:
                continue
            out.append(sent)
            seen.add(key)
            if len(out) >= limit:
                return out
    return out


def _write_jsonl(path: Path, rows: List[str], prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i, text in enumerate(rows):
            f.write(json.dumps({"id": f"{prefix}_{i:07d}", "text": text}, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch raw sources for ingestion corpus")
    parser.add_argument("--output-dir", default="data/raw_sources")
    parser.add_argument("--ud-limit", type=int, default=1200)
    parser.add_argument("--tatoeba-limit", type=int, default=1200)
    parser.add_argument("--wikinews-limit", type=int, default=600)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    ud = _extract_ud_sentences(limit=int(args.ud_limit))
    tat = _extract_tatoeba_mthings_sentences(limit=int(args.tatoeba_limit))
    wnews = _extract_wikinews_sentences(limit=int(args.wikinews_limit))

    _write_jsonl(out_dir / "ud_ewt_sentences.jsonl", ud, "udewt")
    _write_jsonl(out_dir / "tatoeba_en_sentences.jsonl", tat, "tat")
    _write_jsonl(out_dir / "wikinews_en_sentences.jsonl", wnews, "wnews")

    # OANC is intentionally not auto-downloaded here due source distribution specifics.
    # Keep file present as empty placeholder for config compatibility if needed.
    _write_jsonl(out_dir / "oanc_sentences.jsonl", [], "oanc")

    report = {
        "output_dir": str(out_dir),
        "counts": {
            "ud_ewt_sentences": len(ud),
            "tatoeba_sentences": len(tat),
            "wikinews_sentences": len(wnews),
            "oanc_sentences": 0,
            "total": len(ud) + len(tat) + len(wnews),
        },
        "note": "OANC auto-download is not implemented; add it manually if required.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
