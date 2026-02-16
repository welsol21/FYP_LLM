"""Download and persist M2M100 model assets into project-local directory."""

from __future__ import annotations

import argparse
import os
import shutil

from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

DEFAULT_MODEL_ID = "facebook/m2m100_418M"
DEFAULT_OUTPUT_DIR = "artifacts/models/m2m100_418M"


def _has_saved_model(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "config.json"))


def prepare_model(model_id: str = DEFAULT_MODEL_ID, output_dir: str = DEFAULT_OUTPUT_DIR, force: bool = False) -> str:
    out = os.path.abspath(output_dir)
    if _has_saved_model(out):
        if not force:
            return out
        shutil.rmtree(out)

    os.makedirs(out, exist_ok=True)

    tokenizer = M2M100Tokenizer.from_pretrained(model_id)
    model = M2M100ForConditionalGeneration.from_pretrained(model_id)
    tokenizer.save_pretrained(out)
    model.save_pretrained(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare project-local m2m100 model directory.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Hugging Face model id.")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Local output directory for saved model/tokenizer files.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download and overwrite existing local model directory.")
    args = parser.parse_args()

    saved_to = prepare_model(model_id=args.model_id, output_dir=args.output_dir, force=args.force)
    print(f"Saved model to: {saved_to}")


if __name__ == "__main__":
    main()
