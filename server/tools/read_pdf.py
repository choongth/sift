import asyncio
import os
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import httpx


async def read_pdf(source: str, max_pages: int | None = None) -> str:
    limit = max_pages or int(os.environ.get("PDF_MAX_PAGES", "20"))
    if source.startswith("http://") or source.startswith("https://"):
        pdf_bytes = await _fetch_url(source)
        return _extract_text_from_bytes(pdf_bytes, limit)
    else:
        return await asyncio.to_thread(_extract_text_from_path, source, limit)


async def _fetch_url(url: str) -> bytes:
    timeout = float(os.environ.get("PDF_FETCH_TIMEOUT", "30"))
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _extract_text_from_bytes(pdf_bytes: bytes, max_pages: int) -> str:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return _extract(doc, max_pages)


def _extract_text_from_path(path: str, max_pages: int) -> str:
    with fitz.open(path) as doc:
        return _extract(doc, max_pages)


def _extract(doc: fitz.Document, max_pages: int) -> str:
    total = min(len(doc), max_pages)
    pages = []
    for i in range(total):
        text = doc[i].get_text()
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
    return "\n\n".join(pages) if pages else "No extractable text found in PDF."
