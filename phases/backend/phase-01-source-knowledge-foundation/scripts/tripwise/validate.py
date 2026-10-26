from __future__ import annotations

from dataclasses import dataclass, field

from tripwise.cleaning import is_empty_prose, normalize_title, normalize_url
from tripwise.extract import ExtractedPage

PAGE_TYPES = {
    "country",
    "region",
    "city",
    "district",
    "park",
    "topic",
    "itinerary",
    "phrasebook",
    "airport",
    "unknown",
}


@dataclass
class ValidationIssue:
    field: str
    message: str
    fatal: bool = False


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def validate_extracted_page(
    title: str,
    wiki_page_id: int | None,
    canonical_url: str | None,
    wikitext: str | None,
    extracted: ExtractedPage,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if not wiki_page_id:
        issues.append(ValidationIssue("wiki_page_id", "missing page id", fatal=True))
    if not normalize_title(title):
        issues.append(ValidationIssue("title", "empty title", fatal=True))
    if not normalize_url(canonical_url):
        issues.append(ValidationIssue("canonical_url", "invalid or missing URL", fatal=True))
    if not (wikitext or "").strip():
        issues.append(ValidationIssue("raw_wikitext", "empty wikitext", fatal=True))
    if extracted.page_type not in PAGE_TYPES:
        issues.append(
            ValidationIssue("page_type", f"unexpected page type {extracted.page_type}", fatal=True)
        )

    if extracted.latitude is not None and not -90 <= extracted.latitude <= 90:
        extracted.latitude = None
        issues.append(ValidationIssue("latitude", "out of range; stored as null", fatal=False))
    if extracted.longitude is not None and not -180 <= extracted.longitude <= 180:
        extracted.longitude = None
        issues.append(ValidationIssue("longitude", "out of range; stored as null", fatal=False))

    if is_empty_prose(extracted.lead_text) and not extracted.sections:
        issues.append(ValidationIssue("content", "no usable prose extracted", fatal=False))

    fatal = any(i.fatal for i in issues)
    return ValidationResult(ok=not fatal, issues=issues)
