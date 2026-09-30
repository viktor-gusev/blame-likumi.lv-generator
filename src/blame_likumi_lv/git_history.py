from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

from .errors import BlameLikumiError
from .html_parser import extract_official_text
from .models import Law, LawMetadata, Revision

LOGGER = logging.getLogger(__name__)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if result.returncode:
        raise BlameLikumiError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def law_filename(law: Law) -> str:
    return f"{law.id}-{law.slug}.txt"


def _read_metadata(cache_dir: Path, law: Law) -> LawMetadata:
    raw = json.loads((cache_dir / "metadata" / f"{law.id}.json").read_text(encoding="utf-8"))
    for key in ("adopted", "published", "effective"):
        if raw.get(key):
            raw[key] = date.fromisoformat(raw[key])
    return LawMetadata(**{key: value for key, value in raw.items() if key in LawMetadata.__dataclass_fields__})


def _read_revision(cache_dir: Path, revision: Revision) -> tuple[str, bytes]:
    path = cache_dir / "revisions" / revision.law_id / f"{revision.effective.isoformat()}.html"
    if not path.exists():
        raise BlameLikumiError(f"Missing cached revision: {path}")
    raw = path.read_bytes()
    return raw.decode("utf-8"), raw


def _message(law: Law, metadata: LawMetadata, revision: Revision, initial: bool) -> str:
    lines = [("Add" if initial else "Update") + f" {law.title}", "", f"Effective: {revision.effective.isoformat()}"]
    if metadata.adopted:
        lines.append(f"Adopted: {metadata.adopted.isoformat()}")
    if metadata.published:
        lines.append(f"Published: {metadata.published.isoformat()}")
    lines += ["", "Likumi ID: " + law.id, "Source: " + revision.url]
    if metadata.issuer:
        lines.append("Issuer: " + metadata.issuer)
    return "\n".join(lines) + "\n"


def build_history(laws: list[Law], revisions_by_law: dict[str, list[Revision]], cache_dir: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise BlameLikumiError(f"Output repository is not empty: {output}; choose another path")
    output.mkdir(parents=True, exist_ok=True)
    _git(output, "init", "-b", "main")
    (output / "likumi").mkdir()
    (output / "metadata").mkdir()

    metadata_by_law = {law.id: _read_metadata(cache_dir, law) for law in laws}
    generated_readme = """# latvian-laws

This repository is generated from official consolidated law snapshots published
by Likumi.lv. It is intentionally usable with standard Git tools:

```bash
git log -- likumi/<law>.txt
git diff <old> <new> -- likumi/<law>.txt
git blame likumi/<law>.txt
```

The `likumi/` files contain normalized official text only. Provenance and
document metadata are stored in `metadata/` and in the commit messages.

Source: https://likumi.lv/
"""
    (output / "README.md").write_text(generated_readme, encoding="utf-8", newline="\n")
    grouped: dict[date, list[tuple[Law, Revision]]] = defaultdict(list)
    for law in laws:
        revisions = revisions_by_law.get(law.id, [])
        if not revisions:
            raise BlameLikumiError(f"No usable revisions for {law.title}")
        for revision in revisions:
            grouped[revision.effective].append((law, revision))

    for law in laws:
        metadata_path = output / "metadata" / f"{law.id}.json"
        metadata_path.write_text(
            json.dumps(metadata_by_law[law.id].to_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    seen_laws: set[str] = set()
    for effective in sorted(grouped):
        changed: list[tuple[Law, Revision, str]] = []
        for law, revision in sorted(grouped[effective], key=lambda item: item[0].id):
            html, _ = _read_revision(cache_dir, revision)
            text = extract_official_text(html)
            path = output / "likumi" / law_filename(law)
            old = path.read_text(encoding="utf-8") if path.exists() else None
            if old != text:
                path.write_text(text, encoding="utf-8", newline="\n")
                changed.append((law, revision, text))
            # Keep this until after message construction below: it determines
            # whether this is the first snapshot for this law.
        if not changed:
            continue
        _git(output, "add", "-A")
        env = os.environ.copy()
        timestamp = f"{effective.isoformat()}T00:00:00+00:00"
        env.update({
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
            "GIT_AUTHOR_NAME": "Likumi.lv provenance",
            "GIT_AUTHOR_EMAIL": "noreply@likumi.lv",
            "GIT_COMMITTER_NAME": "Likumi.lv provenance",
            "GIT_COMMITTER_EMAIL": "noreply@likumi.lv",
        })
        # One commit per effective date. For a same-day group, list all changed laws.
        messages = [_message(law, metadata_by_law[law.id], revision, law.id not in seen_laws) for law, revision, _ in changed]
        message = "\n".join(messages)
        _git(output, "commit", "--allow-empty", "-m", message, env=env)
        LOGGER.info("%s %s", effective.isoformat(), ", ".join(law.title for law, _, _ in changed))
        seen_laws.update(law.id for law, _, _ in changed)

    # Ensure metadata is present even when a law's text is unexpectedly unchanged.
    _git(output, "status", "--short")
