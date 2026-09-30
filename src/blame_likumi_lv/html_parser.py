from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin

from .errors import UnknownStructureError
from .models import LawMetadata, Revision
from .normalize import normalize_text


_DATE_RE = re.compile(r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\.?")
_ISO_DATE_RE = re.compile(r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})")
_BLOCK_TAGS = {"address", "article", "blockquote", "br", "div", "dd", "dl", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul"}


@dataclass
class Node:
    tag: str = "root"
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def text_content(self) -> str:
        chunks: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                chunks.append(child)
            elif child.tag == "br":
                chunks.append("\n")
            else:
                chunks.append(child.text_content())
        return "".join(chunks)

    def descendants(self) -> Iterable[Node]:
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_tree(source: str) -> Node:
    parser = _TreeParser()
    parser.feed(source)
    parser.close()
    return parser.root


def _find_class(root: Node, class_name: str) -> list[Node]:
    return [node for node in root.descendants() if node.has_class(class_name)]


def _find_id(root: Node, element_id: str) -> list[Node]:
    return [node for node in root.descendants() if node.attrs.get("id") == element_id]


def _render(node: Node) -> str:
    """Render block boundaries without depending on CSS or browser layout."""

    parts: list[str] = []
    inline: list[str] = []

    def flush_inline() -> None:
        if inline:
            value = "".join(inline).strip()
            if value:
                parts.append(value)
            inline.clear()

    for child in node.children:
        if isinstance(child, str):
            inline.append(child)
            continue
        if child.tag == "br":
            inline.append("\n")
        elif child.tag in _BLOCK_TAGS:
            flush_inline()
            value = _render(child).strip()
            if value:
                parts.append(value)
        else:
            inline.append(_render(child))
    flush_inline()
    return "\n\n".join(parts)


def extract_official_text(source: str) -> str:
    tree = parse_tree(source)
    bodies = _find_class(tree, "doc-body")
    if len(bodies) != 1:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: expected one .doc-body, found {len(bodies)}")
    text = normalize_text(_render(bodies[0]))
    if not text:
        raise UnknownStructureError("UNKNOWN_STRUCTURE: .doc-body is empty")
    return text


def parse_lv_date(value: str) -> date | None:
    match = _DATE_RE.search(value)
    if match:
        return date(int(match["year"]), int(match["month"]), int(match["day"]))
    match = _ISO_DATE_RE.search(value)
    if match:
        return date(int(match["year"]), int(match["month"]), int(match["day"]))
    return None


def _field_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*(.*?)(?=\s+(?:Statuss|Izdevējs|Veids|Pieņemts|Stājas spēkā|Tēma|Publicēts|Dokumenta valoda):|$)", text, re.S)
    return " ".join(match.group(1).split()) if match else None


def parse_metadata(source: str, source_url: str, fallback_id: str, fallback_title: str, fallback_type: str) -> LawMetadata:
    tree = parse_tree(source)
    passports = _find_class(tree, "pase-container")
    if len(passports) != 1:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: expected one .pase-container, found {len(passports)}")
    body_nodes = [node for node in passports[0].descendants() if node.has_class("body")]
    if len(body_nodes) != 1:
        raise UnknownStructureError("UNKNOWN_STRUCTURE: expected one passport body")
    fields = [node.text_content() for node in body_nodes[0].descendants() if node.tag == "span"]
    # Older/international document pages render passport fields as adjacent
    # property-title/property-val divs instead of the newer span format.
    passport_nodes = list(body_nodes[0].descendants())
    for index, node in enumerate(passport_nodes):
        if not node.has_class("property-title"):
            continue
        label = " ".join(node.text_content().split())
        for candidate in passport_nodes[index + 1:]:
            if candidate.has_class("property-title"):
                break
            if candidate.has_class("property-val"):
                fields.append(f"{label} {' '.join(candidate.text_content().split())}")
                break
    combined = " ".join(fields)

    def value(label: str) -> str | None:
        for field_text in fields:
            if label in field_text:
                candidate = field_text.split(label, 1)[1].strip()
                if candidate:
                    return " ".join(candidate.split())
        return _field_value(combined, label)

    title = value("Nosaukums:") or fallback_title
    issuer = value("Izdevējs:")
    actual_type = (value("Veids:") or "").lower()
    expected_type = fallback_type.lower()
    if expected_type == "noteikumi" and actual_type and "noteik" not in actual_type:
        raise UnknownStructureError(f"UNSUPPORTED_TYPE: expected {expected_type}, found {actual_type!r}")
    if expected_type == "likums" and actual_type and "noteik" in actual_type:
        raise UnknownStructureError(f"UNSUPPORTED_TYPE: expected {expected_type}, found {actual_type!r}")
    # The catalog's `likums` category also contains international documents;
    # retain the catalog type as the stable project-level classification.
    doc_type = expected_type

    published = value("Publicēts:")
    metadata = LawMetadata(
        id=fallback_id,
        title=title,
        type=doc_type,
        source=source_url,
        status=value("Statuss:"),
        adopted=parse_lv_date(value("Pieņemts:") or ""),
        effective=parse_lv_date(value("Stājas spēkā:") or ""),
        published=parse_lv_date(published or ""),
        issuer=issuer,
        language="LV",
    )
    return metadata


def discover_revisions(
    source: str,
    law_id: str,
    page_url: str,
    fallback_effective: date | None = None,
) -> list[Revision]:
    tree = parse_tree(source)
    containers = _find_class(tree, "redakcija-container")
    if len(containers) > 1:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: expected at most one revision selector, found {len(containers)}")

    revisions: dict[date, Revision] = {}
    # The live page creates the visible dropdown with JavaScript, but embeds
    # its complete official source data in #ver_date. Older page variants put
    # one JSON object in each .element-data node; retain that fallback for
    # fixtures and historical deployments of the site.
    version_nodes = _find_id(tree, "ver_date")
    if len(version_nodes) > 1:
        raise UnknownStructureError(f"UNKNOWN_STRUCTURE: expected one #ver_date, found {len(version_nodes)}")
    if version_nodes and html_lib.unescape(version_nodes[0].text_content()).strip():
        raw = html_lib.unescape(version_nodes[0].text_content()).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UnknownStructureError(f"UNKNOWN_STRUCTURE: invalid #ver_date JSON: {raw[:120]!r}") from exc
        entries = payload.get("data")
        if not isinstance(entries, list) or not entries:
            raise UnknownStructureError("UNKNOWN_STRUCTURE: #ver_date has no revision data")
        for data in entries:
            if not isinstance(data, dict):
                raise UnknownStructureError("UNKNOWN_STRUCTURE: invalid revision entry in #ver_date")
            effective = parse_lv_date(str(data.get("iso_value", ""))) or parse_lv_date(str(data.get("value", "")))
            if effective is None:
                raise UnknownStructureError(f"UNKNOWN_STRUCTURE: revision without date: {data!r}")
            revision_url = urljoin(page_url.rstrip("/") + "/", f"redakcijas-datums/{effective:%Y/%m/%d}")
            revisions[effective] = Revision(law_id=law_id, effective=effective, url=revision_url)
    elif containers:
        for node in containers[0].descendants():
            if not node.has_class("element-data"):
                continue
            raw = html_lib.unescape(node.text_content()).strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise UnknownStructureError(f"UNKNOWN_STRUCTURE: invalid revision element-data: {raw[:120]!r}") from exc
            effective = parse_lv_date(str(data.get("iso_value", ""))) or parse_lv_date(str(data.get("value", "")))
            if effective is None:
                raise UnknownStructureError(f"UNKNOWN_STRUCTURE: revision without date: {raw[:120]!r}")
            revision_url = urljoin(page_url.rstrip("/") + "/", f"redakcijas-datums/{effective:%Y/%m/%d}")
            revisions[effective] = Revision(law_id=law_id, effective=effective, url=revision_url)
    else:
        # Newly published acts can have no revision dropdown yet.  Likumi.lv
        # still exposes their current consolidated version date separately.
        version_date_nodes = _find_id(tree, "version_date")
        if len(version_date_nodes) != 1:
            raise UnknownStructureError(
                f"UNKNOWN_STRUCTURE: expected one revision selector or #version_date, found {len(version_date_nodes)}"
            )
        effective = parse_lv_date(version_date_nodes[0].attrs.get("data-version_date", ""))
        # Some international documents are marked as active but expose an
        # empty version_date.  Their passport still contains the effective
        # date, and the page itself is the only available current snapshot.
        effective = effective or fallback_effective
        if effective is None:
            raise UnknownStructureError("UNKNOWN_STRUCTURE: #version_date has no usable date")
        revisions[effective] = Revision(law_id=law_id, effective=effective, url=page_url)
    if not revisions:
        raise UnknownStructureError("UNKNOWN_STRUCTURE: revision selector contained no revisions")
    return sorted(revisions.values(), key=lambda revision: revision.effective)
