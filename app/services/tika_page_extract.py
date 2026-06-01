"""
Split PDF text into pages from Apache Tika output.

Plain-text Tika responses often omit form-feed (\\f) page breaks, so splitting on
\\f usually yields a single chunk. XHTML output wraps each page in <div class="page">.
"""

import logging

from bs4 import BeautifulSoup
from tika import parser

logger = logging.getLogger("app.services.tika_page_extract")


def _pages_from_xhtml(xhtml_content: str) -> list[str]:
    """Parse Tika XHTML and return one stripped text string per <div class=\"page\">."""
    if not xhtml_content or not xhtml_content.strip():
        return []

    soup = BeautifulSoup(xhtml_content, "lxml")
    page_divs = soup.find_all("div", class_="page")
    pages = [div.get_text().strip() for div in page_divs]
    return [p for p in pages if p]


def _pages_from_formfeed(plain_content: str) -> list[str]:
    """Legacy split: Tika plain text sometimes uses ASCII form-feed between pages."""
    if not plain_content:
        return []
    return [p.strip() for p in plain_content.split("\f") if p.strip()]


def extract_pdf_pages(
    file_path: str,
    *,
    server_endpoint: str,
    headers: dict | None = None,
) -> tuple[list[str], str]:
    """
    Return (page_texts, method_used).

    Tries XHTML page divs first, then plain text + form-feed fallback.
    """
    headers = headers or {}

    # --- Primary: Tika XHTML (one <div class="page"> per PDF page) ---
    raw_xhtml = parser.from_file(
        file_path,
        serverEndpoint=server_endpoint,
        headers=headers,
        xmlContent=True,
    )
    xhtml_content = raw_xhtml.get("content") or ""
    pages = _pages_from_xhtml(xhtml_content)
    if len(pages) > 1:
        logger.debug("Page split via XHTML div.page count=%s", len(pages))
        return pages, "xhtml_div_page"

    if len(pages) == 1:
        # Single div.page is valid for a one-page PDF; still prefer it over form-feed.
        return pages, "xhtml_div_page"

    # --- Fallback: plain text + form-feed (old behaviour) ---
    raw_plain = parser.from_file(
        file_path,
        serverEndpoint=server_endpoint,
        headers=headers,
    )
    plain_content = raw_plain.get("content") or ""
    pages_ff = _pages_from_formfeed(plain_content)
    if len(pages_ff) > 1:
        logger.debug("Page split via form-feed count=%s", len(pages_ff))
        return pages_ff, "formfeed"

    if pages_ff:
        return pages_ff, "formfeed"

    # Last resort: non-empty body as one page (XHTML or plain)
    plain_stripped = plain_content.strip()
    if plain_stripped:
        return [plain_stripped], "plain_single"

    xhtml_stripped = xhtml_content.strip()
    if xhtml_stripped:
        whole = BeautifulSoup(xhtml_content, "lxml").get_text().strip()
        if whole:
            return [whole], "xhtml_single"

    return [], "empty"
