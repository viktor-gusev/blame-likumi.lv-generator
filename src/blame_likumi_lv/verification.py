from __future__ import annotations

import difflib
import logging
from datetime import date
from pathlib import Path

from .errors import VerificationError
from .fetcher import RateLimitedFetcher
from .git_history import law_filename
from .html_parser import discover_revisions, extract_official_text, parse_metadata
from .models import Law

LOGGER = logging.getLogger(__name__)


def verify_law(law: Law, output: Path, fetcher: RateLimitedFetcher, today: date | None = None) -> None:
    today = today or date.today()
    page, _, _ = fetcher.law_page(law)
    parse_metadata(page, law.url, law.id, law.title, law.type)
    revisions = [item for item in discover_revisions(page, law.id, law.url) if item.effective <= today]
    if not revisions:
        raise VerificationError(f"{law.id}: no current effective revision found")
    current = revisions[-1]
    revision_html, _, _ = fetcher.revision_page(current)
    expected = extract_official_text(revision_html)
    path = output / "likumi" / law_filename(law)
    if not path.exists():
        raise VerificationError(f"{law.title}: generated file missing: {path}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=str(path),
            tofile=current.url,
            n=3,
        ))
        raise VerificationError(f"{law.title}: normalized text mismatch at {current.url}\n{diff[:12000]}")
    LOGGER.info("[%s] Verification: PASS (%s)", law.title, current.effective.isoformat())


def verify_all(laws: list[Law], output: Path, fetcher: RateLimitedFetcher) -> None:
    for law in laws:
        verify_law(law, output, fetcher)

