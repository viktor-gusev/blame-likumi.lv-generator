from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Law:
    id: str
    title: str
    slug: str
    type: str
    url: str


@dataclass
class LawMetadata:
    id: str
    title: str
    type: str
    source: str
    status: str | None = None
    adopted: date | None = None
    published: date | None = None
    effective: date | None = None
    issuer: str | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, date):
                data[key] = value.isoformat()
        return data


@dataclass(frozen=True)
class Revision:
    law_id: str
    effective: date
    url: str
    status: str = "historical"


@dataclass
class Snapshot:
    revision: Revision
    text: str
    metadata: LawMetadata
    raw_sha256: str
    normalized_sha256: str

