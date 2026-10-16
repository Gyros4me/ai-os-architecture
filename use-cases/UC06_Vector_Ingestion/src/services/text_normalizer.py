"""
Text normalization helpers for PDF/OCR extraction and RAG prompting.

PDF text layers often contain presentation glyphs instead of normal Unicode:
ligatures, soft hyphens, mojibake, or font-private substitutions.  Keeping this
cleanup in one place makes ingestion and generation prompts behave the same way.
"""

import html as html_lib
import re
import unicodedata
from typing import Any


_SUSPICIOUS_MOJIBAKE = ("Ã", "Â", "â", "Î", "Ï", "Æ", "ï", "ð")

_PDF_GLYPH_REPLACEMENTS = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u00ad": "",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\u2212": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2044": "/",
    "\u0131": "i",
}


def _mojibake_score(text: str) -> int:
    suspicious = sum(text.count(char) for char in _SUSPICIOUS_MOJIBAKE)
    controls = sum(
        1
        for char in text
        if char not in "\n\t\r" and unicodedata.category(char) == "Cc"
    )
    return suspicious + controls * 2 + text.count("\ufffd") * 3


def _repair_mojibake(text: str) -> str:
    if not any(char in text for char in _SUSPICIOUS_MOJIBAKE):
        return text
    best = text
    best_score = _mojibake_score(text)
    for _ in range(2):
        improved = False
        for codec in ("cp1252", "latin-1"):
            try:
                candidate = best.encode(codec).decode("utf-8")
            except UnicodeError:
                continue
            score = _mojibake_score(candidate)
            if score < best_score:
                best = candidate
                best_score = score
                improved = True
        if not improved:
            break
    return best


def normalize_extracted_text(value: Any, compact: bool = False) -> str:
    """Normalize text extracted from PDFs/OCR without changing its meaning."""
    if value is None:
        return ""

    text = str(value)
    if not text:
        return ""

    text = html_lib.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _repair_mojibake(text)

    # Remove line-break hyphenation before whitespace normalization.
    text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", text)

    text = unicodedata.normalize("NFKC", text)

    # Common PDF font substitutions seen in Italian scientific slides.
    text = re.sub(r"(?<=[A-Za-z])\s*\u019f(?=[A-Za-z])", "ti", text)
    text = re.sub(r"(?<=[A-Za-z])\s*\u01ab(?=[A-Za-z]|\b)", "tti", text)
    text = re.sub(r"(?<=[A-Za-z])\s*\u01a9(?=[A-Za-z])", "tt", text)

    for old, new in _PDF_GLYPH_REPLACEMENTS.items():
        text = text.replace(old, new)

    # Drop non-printing controls except useful whitespace.
    text = "".join(
        char
        for char in text
        if char in "\n\t" or unicodedata.category(char)[0] != "C"
    )

    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if compact:
        text = re.sub(r"\s+", " ", text)
    return text.strip()
