#!/usr/bin/env python3
"""Export docs/ela_rle_note_selection_report.html to docs/ela_rle_note_selection_report.pdf via headless Chrome."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import base64
from pathlib import Path


HTML_SRC = Path("docs/ela_rle_note_selection_report.html").resolve()
PDF_OUT = Path("docs/ela_rle_note_selection_report.pdf").resolve()


def main() -> int:
    if not HTML_SRC.exists():
        print(f"Missing HTML source: {HTML_SRC}", file=sys.stderr)
        return 1

    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        print("Chrome/Chromium not found", file=sys.stderr)
        return 1

    html = HTML_SRC.read_text(encoding="utf-8")
    image_rel = "reports/assets/ela_note_id_dynamics_2026-04-30/compare_metrics.png"
    image_path = (HTML_SRC.parent / image_rel).resolve()
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    html = html.replace(
        f'src="{image_rel}"',
        f'src="data:image/png;base64,{image_b64}"',
    )

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        f"--print-to-pdf={PDF_OUT}",
        "--print-to-pdf-no-header",
        "--no-pdf-header-footer",
        str(tmp_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            print(result.stderr[:4000], file=sys.stderr)
            return result.returncode
    finally:
        tmp_path.unlink(missing_ok=True)

    print(f"Wrote {PDF_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
