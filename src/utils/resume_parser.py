"""
resume_parser.py

Extracts raw text from a PDF resume using PyPDF2.
Single-purpose module — no LLM calls, no interpretation.
"""

import hashlib
from PyPDF2 import PdfReader


def extract_text(pdf_path: str) -> str:
    """
    Read every page of a PDF and return the concatenated text.

    Args:
        pdf_path: Absolute or relative path to the resume PDF.

    Returns:
        The full text content of the PDF as a single string.

    Raises:
        FileNotFoundError: If the PDF does not exist.
        PyPDF2.errors.PdfReadError: If the file is not a valid PDF.
    """
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def file_checksum(pdf_path: str) -> str:
    """
    Return the SHA-256 hex digest of a file.

    Used to detect whether the resume has changed since the last
    profile extraction, so we can skip the LLM call when it hasn't.
    """
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
