from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .html_parser import discover_revisions, parse_metadata
from .models import Law, Revision

LOGGER = logging.getLogger(__name__)


class RateLimitedFetcher:
    def __init__(self, cache_dir: Path, refresh: bool = False, min_interval: float = 1.0) -> None:
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.min_interval = min_interval
        self._last_request = 0.0

    def _cache_path(self, kind: str, law_id: str, suffix: str) -> Path:
        path = self.cache_dir / kind / law_id / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get(self, url: str, cache_path: Path) -> tuple[str, bytes, bool]:
        if cache_path.exists() and not self.refresh:
            raw = cache_path.read_bytes()
            return raw.decode("utf-8"), raw, True

        for attempt in range(4):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            request = Request(url, headers={
                "User-Agent": "blame-likumi-lv/0.1 (+https://likumi.lv)",
                "Accept-Language": "lv,en;q=0.5",
            })
            try:
                with urlopen(request, timeout=45) as response:
                    raw = response.read()
                self._last_request = time.monotonic()
                cache_path.write_bytes(raw)
                return raw.decode("utf-8"), raw, False
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    raise
            except URLError:
                if attempt == 3:
                    raise
            time.sleep(2**attempt)
        raise RuntimeError("unreachable")

    def law_page(self, law: Law) -> tuple[str, bytes, bool]:
        return self.get(law.url, self._cache_path("pages", law.id, "page.html"))

    def revision_page(self, revision: Revision) -> tuple[str, bytes, bool]:
        name = revision.effective.isoformat() + ".html"
        return self.get(revision.url, self._cache_path("revisions", revision.law_id, name))


def fetch_law(
    law: Law,
    fetcher: RateLimitedFetcher,
    today: date | None = None,
) -> list[Revision]:
    today = today or date.today()
    page, _, cached = fetcher.law_page(law)
    metadata = parse_metadata(page, law.url, law.id, law.title, law.type)
    revisions = discover_revisions(page, law.id, law.url, fallback_effective=metadata.effective)
    usable = [revision for revision in revisions if revision.effective <= today]
    downloaded = 0
    for revision in usable:
        before = fetcher._cache_path("revisions", revision.law_id, revision.effective.isoformat() + ".html").exists()
        fetcher.revision_page(revision)
        downloaded += 0 if before and not fetcher.refresh else 1
    metadata_path = fetcher.cache_dir / "metadata" / f"{law.id}.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path = fetcher.cache_dir / "revisions" / law.id / "index.json"
    index_path.write_text(json.dumps([
        {"effective": item.effective.isoformat(), "url": item.url}
        for item in usable
    ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info(
        "[%s] Found: %d revisions; Downloaded: %d; Effective revisions: %d; Future revisions skipped: %d",
        law.title,
        len(revisions),
        downloaded + (0 if cached and not fetcher.refresh else 1),
        len(usable),
        len(revisions) - len(usable),
    )
    return usable
