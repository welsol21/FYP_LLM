from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_paired_template_signature_dataset import _build_spacy_signature
from ela_pipeline.annotate.signature_only_renderer import SignatureOnlyT5NoteRenderer
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


MODEL_DIR = "artifacts/models/t5_notes_paired_template_top3cap360_plus_if_family_batch5_v1/trainer_output/checkpoint-1530"
PROBES = [
    "She should have trusted her instincts before making the decision.",
    "The team often works in the office.",
    "Although the weather was cold, they continued the study.",
    "This analysis is very important for the project.",
    "Managers analyze complex data in the city.",
]


def main() -> None:
    renderer = SignatureOnlyT5NoteRenderer(MODEL_DIR, device="auto")
    nlp = load_nlp("en_core_web_sm")
    for sent in PROBES:
        parsed = build_skeleton(sent, nlp)
        sentence_node = next(iter(parsed.values()))
        signature = " -> ".join(_build_spacy_signature(sentence_node, depth=2))
        pred = renderer.render_note(
            signature_text=signature,
            level="intermediate",
            node_level="Sentence",
            depth=2,
            family_id="",
        )
        print(f"SENTENCE: {sent}")
        print(f"SIGNATURE: {signature}")
        print(f"PRED: {pred}")
        print("---")


if __name__ == "__main__":
    main()
