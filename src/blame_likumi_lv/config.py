from __future__ import annotations

import json
from pathlib import Path

from .models import Law


def load_laws(path: Path, only_id: str | None = None) -> list[Law]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    laws = [Law(**item) for item in raw]
    if only_id:
        laws = [law for law in laws if law.id == only_id]
        if not laws:
            raise ValueError(f"Law ID not found in config: {only_id}")
    return laws

