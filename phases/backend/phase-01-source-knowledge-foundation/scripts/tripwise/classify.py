from __future__ import annotations

import re
from dataclasses import dataclass

import mwparserfromhell

STATUS_TYPE_RE = re.compile(
    r"^\s*(outline|usable|guide|star)\s*"
    r"(city|district|country|region|park|topic|itinerary|phrasebook|airport|ruralarea)\s*$",
    re.I,
)

SKIP_LINK_PREFIXES = (
    "file:",
    "image:",
    "category:",
    "wikipedia:",
    "w:",
    ":w:",
    "c:",
    ":c:",
    "special:",
    "template:",
    "mediawiki:",
    "help:",
    "wikidata:",
    "commons:",
    "module:",
)


@dataclass(frozen=True)
class PageClassification:
    page_type: str
    article_status: str | None
    is_huge_city: bool
    matched_template: str | None


def _template_name(template) -> str:
    return str(template.name).strip().lower().replace(" ", "")


def classify_page(title: str, wikitext: str) -> PageClassification:
    """Classify from Wikivoyage status templates, not from assumed names."""
    code = mwparserfromhell.parse(wikitext or "")
    matched = None
    status = None
    page_type = None
    has_print_districts = False

    for template in code.filter_templates():
        name = _template_name(template)
        if name == "printdistricts":
            has_print_districts = True
        match = STATUS_TYPE_RE.match(name)
        if match and page_type is None:
            status = match.group(1).lower()
            page_type = match.group(2).lower()
            matched = name

    if page_type == "ruralarea":
        page_type = "region"

    if page_type is None:
        if "/" in (title or "") and not title.startswith("Wikipedia"):
            page_type = "district"
        else:
            page_type = "unknown"

    is_huge_city = bool(has_print_districts and page_type == "city")
    return PageClassification(
        page_type=page_type,
        article_status=status,
        is_huge_city=is_huge_city,
        matched_template=matched,
    )


def extract_is_part_of(wikitext: str) -> str | None:
    code = mwparserfromhell.parse(wikitext or "")
    for template in code.filter_templates():
        if _template_name(template) == "ispartof" and template.params:
            value = str(template.get(1).value).strip()
            value = value.replace("_", " ")
            return value or None
    return None


def extract_geo(wikitext: str) -> tuple[float | None, float | None]:
    code = mwparserfromhell.parse(wikitext or "")
    for template in code.filter_templates():
        if _template_name(template) != "geo":
            continue
        params = [str(p.value).strip() for p in template.params if not p.showkey]
        if len(params) >= 2:
            try:
                lat = float(params[0].split("|")[0])
                lon = float(params[1].split("|")[0])
            except ValueError:
                return None, None
            return lat, lon
        try:
            lat = float(str(template.get(1).value).strip())
            lon = float(str(template.get(2).value).strip())
            return lat, lon
        except (ValueError, Exception):
            return None, None
    return None, None


def extract_related_titles(wikitext: str) -> list[str]:
    from tripwise.cleaning import normalize_title

    titles: list[str] = []
    code = mwparserfromhell.parse(wikitext or "")
    for template in code.filter_templates():
        name = _template_name(template)
        if name not in {"related", "seealso"}:
            continue
        if template.params:
            titles.append(normalize_title(str(template.get(1).value)))
    return [t for t in titles if t]


def is_skippable_link_target(target: str) -> bool:
    lowered = target.strip().lstrip(":").lower()
    return lowered.startswith(SKIP_LINK_PREFIXES) or lowered.startswith("http")
