"""Format parsers for the universal book-extraction engine."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from shutil import which
from typing import Protocol
from xml.etree import ElementTree as ET

from .engine import BookTextPayload


class BookParser(Protocol):
    name: str

    def supports(self, path: str) -> bool:
        ...

    def parse(self, path: str) -> BookTextPayload:
        ...


def _run_text_command(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(stderr or f"Command failed: {' '.join(argv)}")
    return proc.stdout


def _command_available(name: str) -> bool:
    return which(name) is not None


def _looks_like_meaningful_text(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{2,}", str(text or ""))
    return len(words) >= 20 or sum(len(word) for word in words) >= 100


def _strip_html_text(raw: str) -> str:
    stripper = _EpubHtmlStripper()
    stripper.feed(raw)
    return stripper.text()


def _ocr_image_to_text(path: str, *, lang: str = "eng") -> str:
    if not _command_available("tesseract"):
        raise RuntimeError("tesseract is not installed")
    return _run_text_command(["tesseract", str(path), "stdout", "-l", lang, "--psm", "3"])


def _ocr_pdf_to_text(path: str, *, lang: str = "eng", max_pages: int = 40) -> tuple[str, dict]:
    if not _command_available("pdftoppm"):
        raise RuntimeError("pdftoppm is not installed")
    if not _command_available("tesseract"):
        raise RuntimeError("tesseract is not installed")

    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        _run_text_command(
            [
                "pdftoppm",
                "-f",
                "1",
                "-l",
                str(max_pages),
                "-png",
                str(path),
                str(prefix),
            ]
        )
        image_paths = sorted(Path(tmp).glob("page-*.png"))
        text_chunks = []
        for image_path in image_paths:
            text = _ocr_image_to_text(str(image_path), lang=lang)
            if text.strip():
                text_chunks.append(text.strip())
        return "\n\n".join(text_chunks), {
            "ocr_used": True,
            "ocr_pages": len(image_paths),
            "ocr_page_limit": max_pages,
        }


def _extract_docx_xml_text(source: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(source) as archive:
        xml_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("word/") and name.endswith(".xml") and "rels" not in name
        )
        for name in xml_names:
            raw = archive.read(name)
            root = ET.fromstring(raw)
            texts = [item.text.strip() for item in root.iter() if item.text and item.text.strip()]
            if texts:
                chunks.append(" ".join(texts))
    return "\n\n".join(chunks)


@dataclass(slots=True)
class PdfBookParser:
    name: str = "pdf"
    ocr_lang: str = "eng"
    ocr_max_pages: int = 40
    enable_ocr: bool = True

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        text = _run_text_command(["pdftotext", str(source), "-"])
        metadata: dict[str, object] = {}
        if self.enable_ocr and not _looks_like_meaningful_text(text):
            try:
                ocr_text, ocr_meta = _ocr_pdf_to_text(str(source), lang=self.ocr_lang, max_pages=self.ocr_max_pages)
            except RuntimeError as exc:
                metadata["ocr_error"] = str(exc)
            else:
                if _looks_like_meaningful_text(ocr_text):
                    text = ocr_text
                    metadata.update(ocr_meta)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="pdf",
            text=text,
            metadata=metadata,
        )


class _EpubHtmlStripper(HTMLParser):
    BLOCK_TAGS = {
        "body",
        "div",
        "section",
        "article",
        "p",
        "li",
        "ul",
        "ol",
        "table",
        "tr",
        "td",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


@dataclass(slots=True)
class EpubBookParser:
    name: str = "epub"

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".epub"

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        chunks: list[str] = []
        with zipfile.ZipFile(source) as archive:
            html_names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            )
            for name in html_names:
                raw = archive.read(name).decode("utf-8", errors="ignore")
                text = _strip_html_text(raw)
                if text:
                    chunks.append(text)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="epub",
            text="\n\n".join(chunks),
        )


@dataclass(slots=True)
class DjvuBookParser:
    name: str = "djvu"

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".djvu"

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        text = _run_text_command(["djvutxt", str(source)])
        text = re.sub(r"\f", "\n", text)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="djvu",
            text=text,
        )


@dataclass(slots=True)
class OcrImageBookParser:
    name: str = "ocr_image"
    ocr_lang: str = "eng"
    image_suffixes: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.image_suffixes

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        text = _ocr_image_to_text(str(source), lang=self.ocr_lang)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="image",
            text=text,
            metadata={"ocr_used": True},
        )


@dataclass(slots=True)
class DocxBookParser:
    name: str = "docx"

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".docx"

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        text = _extract_docx_xml_text(source)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="docx",
            text=text,
        )


@dataclass(slots=True)
class DocBookParser:
    name: str = "doc"

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() in {".doc", ".rtf", ".odt"}

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        if not _command_available("soffice"):
            raise RuntimeError("soffice is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            profile_dir = Path(tmp) / "soffice-profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            argv = [
                "soffice",
                f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                tmp,
                str(source),
            ]
            env = os.environ.copy()
            env.update(
                {
                    "HOME": tmp,
                    "TMPDIR": tmp,
                    "XDG_RUNTIME_DIR": str(runtime_dir),
                    "SAL_USE_VCLPLUGIN": "svp",
                }
            )
            proc = subprocess.run(argv, capture_output=True, text=True, check=False, env=env)
            output = Path(tmp) / f"{source.stem}.txt"
            if not output.exists():
                candidates = sorted(Path(tmp).glob("*.txt"))
                if candidates:
                    output = candidates[0]
            if proc.returncode != 0 and not output.exists():
                stderr = (proc.stderr or "").strip()
                raise RuntimeError(stderr or f"Command failed: {' '.join(argv)}")
            text = output.read_text(encoding="utf-8", errors="ignore") if output.exists() else ""
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="doc",
            text=text,
        )


@dataclass(slots=True)
class ZipBookParser:
    name: str = "zip"
    child_parsers: list[BookParser] | None = None
    archive_suffixes: tuple[str, ...] = (".zip", ".cbz")
    max_members: int = 120

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.archive_suffixes

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        if not self.child_parsers:
            raise RuntimeError("zip parser is not attached to child parsers")

        extracted_chunks: list[str] = []
        parsed_members: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(source) as archive:
                members = [
                    info for info in archive.infolist() if not info.is_dir() and not Path(info.filename).name.startswith(".")
                ]
                for info in members[: self.max_members]:
                    target = Path(tmp) / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as src, target.open("wb") as dst:
                        dst.write(src.read())
                    parser = next(
                        (
                            parser
                            for parser in self.child_parsers
                            if parser is not self and parser.supports(str(target))
                        ),
                        None,
                    )
                    if parser is None:
                        continue
                    try:
                        payload = parser.parse(str(target))
                    except Exception:
                        continue
                    if not _norm(payload.text):
                        continue
                    parsed_members.append(info.filename)
                    extracted_chunks.append(f"[{info.filename}]\n{payload.text}")
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="zip",
            text="\n\n".join(extracted_chunks),
            metadata={"parsed_members": parsed_members},
        )


@dataclass(slots=True)
class PlainTextBookParser:
    name: str = "text"
    suffixes: tuple[str, ...] = (".txt", ".md", ".html", ".htm")

    def supports(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.suffixes

    def parse(self, path: str) -> BookTextPayload:
        source = Path(path)
        text = source.read_text(encoding="utf-8", errors="ignore")
        if source.suffix.lower() in {".html", ".htm"}:
            text = _strip_html_text(text)
        return BookTextPayload(
            source_path=str(source),
            parser_name=self.name,
            format="text",
            text=text,
        )


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def build_default_parsers(*, enable_ocr: bool = True, ocr_lang: str = "eng", ocr_max_pages: int = 40) -> list[BookParser]:
    parsers: list[BookParser] = [
        PdfBookParser(enable_ocr=enable_ocr, ocr_lang=ocr_lang, ocr_max_pages=ocr_max_pages),
        EpubBookParser(),
        DjvuBookParser(),
        OcrImageBookParser(ocr_lang=ocr_lang),
        DocxBookParser(),
        DocBookParser(),
        PlainTextBookParser(),
    ]
    zip_parser = ZipBookParser()
    parsers.append(zip_parser)
    zip_parser.child_parsers = parsers
    return parsers
