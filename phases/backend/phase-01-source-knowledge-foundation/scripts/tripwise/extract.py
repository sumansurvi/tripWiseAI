from __future__ import annotations

from dataclasses import dataclass, field

import mwparserfromhell
from mwparserfromhell.nodes import Heading, Template

from tripwise.classify import (
    classify_page,
    extract_geo,
    extract_is_part_of,
    extract_related_titles,
    is_skippable_link_target,
)
from tripwise.cleaning import heading_display, normalize_title, sha256_text, strip_wikitext

LISTING_TEMPLATES = {"see", "do", "eat", "drink", "sleep", "buy", "listing"}
CHILD_SECTIONS = {"districts", "regions", "cities", "other destinations"}


@dataclass
class ExtractedSection:
    heading_level: int
    section_title: str
    subsection_title: str | None
    heading_path: str
    sort_order: int
    wikitext: str
    cleaned_text: str
    content_hash: str


@dataclass
class ExtractedListing:
    listing_kind: str
    name: str | None
    alt_name: str | None
    description: str | None
    address: str | None
    directions: str | None
    latitude: float | None
    longitude: float | None
    url: str | None
    phone: str | None
    hours: str | None
    price_raw: str | None
    lastedit: str | None
    wikidata_id: str | None
    wikipedia_title: str | None
    extra: dict
    sort_order: int
    section_path: str
    heading_level: int


@dataclass
class ExtractedRelationship:
    to_title: str
    relationship_type: str


@dataclass
class ExtractedPage:
    title: str
    page_type: str
    article_status: str | None
    is_huge_city: bool
    parent_title: str | None
    latitude: float | None
    longitude: float | None
    lead_text: str
    sections: list[ExtractedSection] = field(default_factory=list)
    listings: list[ExtractedListing] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)


def _param(template: Template, key: str) -> str | None:
    if not template.has(key):
        return None
    value = str(template.get(key).value).strip()
    return value or None


def _float_param(template: Template, key: str) -> float | None:
    raw = _param(template, key)
    if raw is None:
        return None
    try:
        return float(raw.split()[0])
    except ValueError:
        return None


def _listing_from_template(template: Template, kind: str, sort_order: int, section_path: str, level: int) -> ExtractedListing:
    known = {
        "name",
        "alt",
        "content",
        "address",
        "directions",
        "lat",
        "long",
        "url",
        "phone",
        "hours",
        "price",
        "lastedit",
        "wikidata",
        "wikipedia",
        "email",
        "fax",
        "tollfree",
        "checkin",
        "checkout",
        "image",
    }
    extra: dict[str, str] = {}
    for param in template.params:
        key = str(param.name).strip().lower()
        if key in known or key.isdigit():
            continue
        extra[key] = str(param.value).strip()
    description = _param(template, "content")
    if description:
        description = strip_wikitext(description, keep_headings=False)
    return ExtractedListing(
        listing_kind=kind,
        name=_param(template, "name"),
        alt_name=_param(template, "alt"),
        description=description,
        address=_param(template, "address"),
        directions=_param(template, "directions"),
        latitude=_float_param(template, "lat"),
        longitude=_float_param(template, "long"),
        url=_param(template, "url"),
        phone=_param(template, "phone"),
        hours=_param(template, "hours"),
        price_raw=_param(template, "price"),
        lastedit=_param(template, "lastedit"),
        wikidata_id=_param(template, "wikidata"),
        wikipedia_title=_param(template, "wikipedia"),
        extra=extra,
        sort_order=sort_order,
        section_path=section_path,
        heading_level=level,
    )


def _wikilink_targets(wikitext: str) -> list[str]:
    titles: list[str] = []
    code = mwparserfromhell.parse(wikitext or "")
    for node in code.filter_wikilinks():
        raw_title = str(node.title).split("#", 1)[0]
        target = normalize_title(raw_title)
        if not target or target.startswith("#") or is_skippable_link_target(target):
            continue
        titles.append(target)
    return titles


def _path_from_stack(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def extract_page(title: str, wikitext: str) -> ExtractedPage:
    classification = classify_page(title, wikitext)
    parent = extract_is_part_of(wikitext)
    lat, lon = extract_geo(wikitext)
    code = mwparserfromhell.parse(wikitext or "")

    sections: list[ExtractedSection] = []
    listings: list[ExtractedListing] = []
    relationships: list[ExtractedRelationship] = []

    stack: list[tuple[int, str]] = [(1, "Lead")]
    buckets: dict[str, list] = {"Lead": []}
    listing_count = 0

    def current_path() -> str:
        return _path_from_stack(stack)

    for node in code.nodes:
        if isinstance(node, Heading):
            level = int(node.level)
            name = heading_display(str(node.title))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, name))
            path = current_path()
            buckets.setdefault(path, [])
            continue

        path = current_path()
        buckets.setdefault(path, []).append(node)

        if isinstance(node, Template):
            kind = str(node.name).strip().lower()
            if kind in LISTING_TEMPLATES:
                listing_count += 1
                listings.append(
                    _listing_from_template(node, kind, listing_count, path, stack[-1][0])
                )

    for template in code.filter_templates():
        name = str(template.name).strip().lower().replace(" ", "")
        if name != "regionlist":
            continue
        rel_type = "district_child" if classification.is_huge_city else "region_child"
        for target in _wikilink_targets(str(template)):
            if rel_type == "district_child" and not target.startswith(title + "/"):
                continue
            relationships.append(ExtractedRelationship(target, rel_type))

    sort_order = 0
    lead_text = ""
    for path, nodes in buckets.items():
        raw = "".join(str(n) for n in nodes)
        cleaned = strip_wikitext(raw)
        parts = path.split(" > ")
        level = len(parts)
        section_title = parts[1] if len(parts) > 1 else parts[0]
        subsection = parts[-1] if len(parts) > 2 else None
        if path == "Lead":
            lead_text = cleaned
            section_title = "Lead"
            subsection = None
            level = 1
        lowered = section_title.lower()
        if lowered in CHILD_SECTIONS:
            rel_type = {
                "districts": "district_child",
                "regions": "region_child",
                "cities": "city_child",
                "other destinations": "other_destination_child",
            }[lowered]
            for target in _wikilink_targets(raw):
                if rel_type == "district_child" and not target.startswith(title + "/"):
                    continue
                relationships.append(ExtractedRelationship(target, rel_type))
        if lowered == "go next":
            for target in _wikilink_targets(raw):
                relationships.append(ExtractedRelationship(target, "go_next"))
        if not cleaned:
            continue
        sort_order += 1
        sections.append(
            ExtractedSection(
                heading_level=level,
                section_title=section_title,
                subsection_title=subsection,
                heading_path=path,
                sort_order=sort_order,
                wikitext=raw,
                cleaned_text=cleaned,
                content_hash=sha256_text(cleaned),
            )
        )

    if parent:
        relationships.append(ExtractedRelationship(parent, "is_part_of"))
    for related in extract_related_titles(wikitext):
        relationships.append(ExtractedRelationship(related, "related"))

    # Deduplicate relationships while preserving order
    seen: set[tuple[str, str]] = set()
    unique_rels: list[ExtractedRelationship] = []
    for rel in relationships:
        key = (rel.to_title, rel.relationship_type)
        if key in seen:
            continue
        seen.add(key)
        unique_rels.append(rel)

    return ExtractedPage(
        title=title,
        page_type=classification.page_type,
        article_status=classification.article_status,
        is_huge_city=classification.is_huge_city,
        parent_title=parent,
        latitude=lat,
        longitude=lon,
        lead_text=lead_text,
        sections=sections,
        listings=listings,
        relationships=unique_rels,
    )


def discoverable_titles(extracted: ExtractedPage, *, follow_go_next: bool, scope_mode: str) -> list[str]:
    titles: list[str] = []
    child_types = {"district_child", "region_child", "city_child", "other_destination_child"}
    for rel in extracted.relationships:
        if rel.relationship_type == "go_next" and not follow_go_next:
            continue
        if scope_mode == "seeds_only":
            continue
        if scope_mode == "seeds_and_districts" and rel.relationship_type != "district_child":
            continue
        # scope_root (and any other mode): follow destination hierarchy children
        if rel.relationship_type in child_types or (follow_go_next and rel.relationship_type == "go_next"):
            titles.append(rel.to_title)
    return titles
