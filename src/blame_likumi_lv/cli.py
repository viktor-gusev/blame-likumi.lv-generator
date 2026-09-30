from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .catalog import discover_active_documents, write_catalog_config
from .config import load_laws
from .errors import BlameLikumiError
from .fetcher import RateLimitedFetcher, fetch_law
from .git_history import build_history
from .verification import verify_all


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Git history from official Likumi.lv law snapshots")
    parser.add_argument("--config", type=Path, default=Path("config/active-documents.json"))
    parser.add_argument("--cache", type=Path, default=Path("cache"))
    parser.add_argument("--output", type=Path, default=Path("../latvian-laws"))
    parser.add_argument("--law", dest="law_id", help="process one configured Likumi.lv document ID")
    parser.add_argument("--refresh", action="store_true", help="ignore cached pages and download again")
    parser.add_argument("--workers", type=int, default=1, help="parallel document workers; each worker keeps the rate limit")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("catalog", "fetch", "build", "verify", "generate"):
        command = sub.add_parser(name)
        # Accept the documented and natural form `generate --law ...` as well
        # as global options placed before the subcommand. SUPPRESS prevents a
        # subparser default from overwriting a value already parsed globally.
        command.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--cache", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--output", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--law", dest="law_id", default=argparse.SUPPRESS)
        command.add_argument("--refresh", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--workers", type=int, default=argparse.SUPPRESS)
        command.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
        if name == "catalog":
            command.add_argument("--catalog-output", type=Path, default=Path("config/active-documents.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        if args.command == "catalog":
            fetcher = RateLimitedFetcher(args.cache, refresh=args.refresh)
            laws = discover_active_documents(fetcher)
            write_catalog_config(laws, args.catalog_output)
            logging.info("Active catalog: %d documents written to %s", len(laws), args.catalog_output)
            return 0
        laws = load_laws(args.config, args.law_id)
        fetcher = RateLimitedFetcher(args.cache, refresh=args.refresh)
        revisions_by_law = {}
        if args.command in {"fetch", "generate"}:
            if args.workers < 1:
                raise ValueError("--workers must be at least 1")
            if args.workers == 1:
                for law in laws:
                    revisions_by_law[law.id] = fetch_law(law, fetcher)
            else:
                def fetch_one(law):
                    worker = RateLimitedFetcher(args.cache, refresh=args.refresh)
                    return law.id, fetch_law(law, worker)

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for law_id, revisions in pool.map(fetch_one, laws):
                        revisions_by_law[law_id] = revisions
        if args.command in {"build", "generate"}:
            if not revisions_by_law:
                for law in laws:
                    index = args.cache / "revisions" / law.id / "index.json"
                    if not index.exists():
                        raise BlameLikumiError(f"No cached index for {law.title}; run fetch first")
                    import json
                    from datetime import date
                    from .models import Revision
                    revisions_by_law[law.id] = [Revision(law.id, date.fromisoformat(item["effective"]), item["url"]) for item in json.loads(index.read_text(encoding="utf-8"))]
            build_history(laws, revisions_by_law, args.cache, args.output)
        if args.command in {"verify", "generate"}:
            # Verification is explicitly against the current official page,
            # so it must bypass a possibly stale historical cache.
            verify_fetcher = RateLimitedFetcher(args.cache, refresh=True)
            verify_all(laws, args.output, verify_fetcher, workers=args.workers)
        return 0
    except (BlameLikumiError, OSError, ValueError) as exc:
        logging.error("ERROR: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
