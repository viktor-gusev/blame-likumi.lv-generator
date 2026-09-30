from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urljoin

from .errors import UnknownStructureError
from .fetcher import RateLimitedFetcher
from .models import Law


BASE_URL = "https://likumi.lv"
ALPHABET = "AĀBCČDEĒFGĢHIĪJKĶLĻMNŅOPRSŠTUŪVZŽ"
ACTIVE_CATALOGS = (
    ("138", "84", "likums"),
    ("92", "87", "noteikumi"),
)
_LINK_RE = re.compile(r"<a\b[^>]*\bhref=['\"](?P<href>[^'\"]+)['\"][^>]*>(?P<title>.*?)</a>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _request_url(issuer_id: str, type_id: str, piece: int, *, stats: bool, today: date) -> str:
    params = {
        "piece": piece,
        "mode": "i",
        "alpha": ALPHABET,
        "izd_id": issuer_id,
        "veids_id": type_id,
        "spe": 1,
        "ngr": 1,
        "oby": "title_noquote",
        "odir": "asc",
        "tstamp": today.strftime("%Y%m%d"),
    }
    if stats:
        params["qwstats"] = 1
    return f"{BASE_URL}/ajax/ties_akti_pec_veida.php?{urlencode(params)}"


def _cache_path(cache_dir: Path, issuer_id: str, type_id: str, piece: int, *, stats: bool) -> Path:
    suffix = "stats.json" if stats else f"piece-{piece:04d}.json"
    path = cache_dir / "catalog" / f"{issuer_id}-{type_id}-active" / suffix
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(fetcher: RateLimitedFetcher, url: str, cache_path: Path) -> object:
    text, _, _ = fetcher.get(url, cache_path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: invalid catalog JSON at {url}") from exc


def _slugify(value: str) -> str:
    replacements = str.maketrans({
        "ā": "a", "č": "c", "ē": "e", "ģ": "g", "ī": "i", "ķ": "k",
        "ļ": "l", "ņ": "n", "ŗ": "r", "š": "s", "ū": "u", "ž": "z",
        "Ā": "A", "Č": "C", "Ē": "E", "Ģ": "G", "Ī": "I", "Ķ": "K",
        "Ļ": "L", "Ņ": "N", "Ŗ": "R", "Š": "S", "Ū": "U", "Ž": "Z",
    })
    value = value.translate(replacements).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "document"


def _row_to_law(row: object, document_type: str) -> Law:
    if not isinstance(row, dict):
        raise UnknownStructureError("UNKNOWN_STRUCTURE: catalog row is not an object")
    document_id = str(row.get("doc_id") or "")
    title_html = str(row.get("title") or "")
    match = _LINK_RE.search(title_html)
    if not document_id or not match:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: catalog row lacks document link: {row!r}")
    href = html.unescape(match.group("href")).replace("\\/", "/")
    title = " ".join(_TAG_RE.sub("", html.unescape(match.group("title"))).split())
    source_url = urljoin(BASE_URL, href)
    tail = source_url.rstrip("/").rsplit("/", 1)[-1]
    prefix = f"{document_id}-"
    slug = tail[len(prefix):] if tail.startswith(prefix) else _slugify(title)
    return Law(id=document_id, title=title, slug=slug, type=document_type, url=source_url)


def discover_active_documents(fetcher: RateLimitedFetcher, today: date | None = None) -> list[Law]:
    today = today or date.today()
    documents: dict[str, Law] = {}
    for issuer_id, type_id, document_type in ACTIVE_CATALOGS:
        stats_url = _request_url(issuer_id, type_id, 0, stats=True, today=today)
        stats = _read_json(fetcher, stats_url, _cache_path(fetcher.cache_dir, issuer_id, type_id, 0, stats=True))
        if not isinstance(stats, dict) or not isinstance(stats.get("pieces"), int):
            raise UnknownStructureError(f"UNKNOWN_STRUCTURE: invalid catalog stats at {stats_url}")
        for piece in range(stats["pieces"]):
            url = _request_url(issuer_id, type_id, piece, stats=False, today=today)
            payload = _read_json(fetcher, url, _cache_path(fetcher.cache_dir, issuer_id, type_id, piece, stats=False))
            if not isinstance(payload, list):
                raise UnknownStructureError(f"UNKNOWN_STRUCTURE: catalog chunk is not a list at {url}")
            for row in payload:
                law = _row_to_law(row, document_type)
                documents[law.id] = law
    return sorted(documents.values(), key=lambda law: (law.type, law.title.casefold(), law.id))


def write_catalog_config(laws: list[Law], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(law) for law in laws], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
