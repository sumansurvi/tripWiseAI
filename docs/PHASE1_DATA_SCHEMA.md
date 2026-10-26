# Phase 1 data schema

Only fields observed in Wikivoyage **wikitext** or **Action API** metadata are stored.

**Acquisition:** English Wikivoyage Action API (`https://en.wikivoyage.org/w/api.php`) via `httpx`.  
**Not used:** Playwright, Selenium, HTML scraping, or browser automation.

## Principles

1. Structure what the source structures (`{{see}}` parameters, `{{geo}}`, `{{isPartOf}}`, status templates).
2. Preserve cleaned source prose for everything else.
3. Missing source data is `NULL`, never inferred.
4. No LLM rewrite, summary, or recommendation during ingest.
5. Every page keeps license, URL, revision, and hash.
6. Every on-disk JSON record and future RAG chunk includes **`source_url`**.

## Layering

```text
Action API revision
  → pages.raw_wikitext
  → page_sections.wikitext + listings (parsed)
  → page_sections.cleaned_text + listing.description (normalized whitespace only)
  → data/raw + data/structured + data/chunks  (files, each with source_url)
```

Phase 3 embeddings read `data/chunks` (and/or DB section/listing text). They do not re-fetch Wikivoyage per question.

## Records

### Source

One row: English Wikivoyage, CC BY-SA 4.0.

### Page

| Field | Origin | Required |
| --- | --- | --- |
| wiki_page_id | API `pageid` | yes |
| title | API canonical title | yes |
| canonical_url | API `fullurl` (= `source_url` in JSON) | yes |
| page_type | status template, else `unknown` | yes |
| article_status | outline/usable/guide/star | no |
| parent_title | `{{isPartOf}}` | no |
| latitude, longitude | `{{geo}}` | no |
| is_huge_city | city + `{{printDistricts}}` | yes (boolean, default false) |
| revision_id, revision_timestamp | API revision | no (should be present) |
| retrieved_at, first_seen_at, last_seen_at | ingest clock | yes |
| content_hash | sha256(raw wikitext) | yes |
| raw_wikitext | API slot main | yes |
| lead_text | cleaned lead | no |
| license, attribution | siteinfo + revision URL | yes |

### Page section

| Field | Origin |
| --- | --- |
| heading_level / section_title / subsection_title / heading_path | wikitext headings |
| wikitext | raw slice |
| cleaned_text | templates/links stripped, meaning unchanged |
| content_hash | sha256(cleaned_text) |

Empty sections are not stored.

### Listing

Created only when a `{{see|do|eat|drink|sleep|buy|listing}}` template is present.

| Field | Origin | Notes |
| --- | --- | --- |
| listing_kind | template name | not invented categories |
| name, alt_name, address, directions, url, phone, hours | template params | NULL if absent |
| latitude, longitude | `lat` / `long` | NULL if unparseable |
| price_raw | `price` | **text**, never a number column |
| description | `content` after light cleaning | RAG context |
| lastedit, wikidata_id, wikipedia_title | params | optional |
| extra | other named params | JSON, including checkin/checkout |

### Relationship

| Type | Origin |
| --- | --- |
| is_part_of | `{{isPartOf}}` |
| district_child / region_child / city_child / other_destination_child | links in those H2 sections |
| go_next | links in Go next |
| related | `{{related}}` |

Targets are titles, not fabricated page ids for redlinks.

### Ingestion run / errors

Run: `RUNNING | COMPLETED | PARTIAL | FAILED` plus discover/process/success/fail/skip and create/update/unchanged counts.

Errors: per-page `error_type` + message. One failed page does not abort the run.

## On-disk JSON (`data/`)

After ingest (or `export-data`), each page is also written under:

| Folder | Contents |
| --- | --- |
| `data/raw/` | API metadata + full wikitext + `source_url` |
| `data/structured/` | sections, listings, relationships + `source_url` |
| `data/chunks/` | section/listing text units; **every chunk includes `source_url`** → Phase 3 |

## Citation

User-facing answers must return the `source_url` of every evidence record used. Missing retrieval → no fabricated URL.

## What is explicitly out of contract

- Live prices, availability, or INR conversion
- Image binaries and image licenses
- “Nightlife = true” style flags
- AI comparisons or itineraries
- Embeddings / pgvector (Phase 3)
- Browser / Playwright acquisition
