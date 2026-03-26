#!/usr/bin/env python3
"""
Download HuggingFace ONNX models (q8/quantized variants) to frontend/public/models/
so the app can load them locally without downloading from HuggingFace at runtime.

Usage:
  python3 frontend/scripts/download_models.py
  # or from the frontend/ directory:
  python3 scripts/download_models.py
"""
import os
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download

SCRIPT_DIR = Path(__file__).parent.resolve()
MODELS_DIR = SCRIPT_DIR.parent / 'public' / 'models'

# (repo_id, [files to download])
# Only q8/quantized variants needed for WASM inference.
MODELS = [
    (
        'Xenova/whisper-base.en',
        [
            'config.json',
            'generation_config.json',
            'preprocessor_config.json',
            'quant_config.json',
            'added_tokens.json',
            'merges.txt',
            'normalizer.json',
            'tokenizer.json',
            'tokenizer_config.json',
            'vocab.json',
            'onnx/encoder_model_quantized.onnx',
            'onnx/decoder_model_merged_quantized.onnx',
        ],
    ),
    (
        'Xenova/opus-mt-en-ru',
        [
            'config.json',
            'generation_config.json',
            'quantize_config.json',
            'source.spm',
            'target.spm',
            'special_tokens_map.json',
            'tokenizer.json',
            'tokenizer_config.json',
            'vocab.json',
            'onnx/encoder_model_quantized.onnx',
            'onnx/decoder_model_merged_quantized.onnx',
        ],
    ),
    (
        'Xenova/mms-tts-rus',
        [
            'config.json',
            'added_tokens.json',
            'special_tokens_map.json',
            'tokenizer.json',
            'tokenizer_config.json',
            'vocab.json',
            'quantize_config.json',
            'onnx/model_quantized.onnx',
        ],
    ),
]


def download_model(repo_id: str, files: list[str]) -> None:
    dest_dir = MODELS_DIR / repo_id
    print(f'\n--- {repo_id} → {dest_dir}')
    for filename in files:
        dest_file = dest_dir / filename
        if dest_file.exists():
            print(f'  skip (exists): {filename}')
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        print(f'  downloading: {filename} ...', end='', flush=True)
        try:
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(dest_dir),
                local_dir_use_symlinks=False,
            )
            size_mb = Path(path).stat().st_size / 1024 / 1024
            print(f' {size_mb:.1f} MB')
        except Exception as e:
            print(f' ERROR: {e}', file=sys.stderr)


def main() -> None:
    print(f'Models output dir: {MODELS_DIR}')
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for repo_id, files in MODELS:
        download_model(repo_id, files)
    print('\nDone.')


if __name__ == '__main__':
    main()
