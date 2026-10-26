"""Architecture alignment checks for Phase 1 exports and validation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from tripwise.export_json import export_page_json
from tripwise.extract import extract_page
from tripwise.source_client import RetrievedPage
from tripwise.validate import validate_extracted_page

from fixtures_util import load_fixture


def _retrieved(
    title, wiki_page_id, wikitext, url
):
    # type: (str, int, str, Optional[str]) -> RetrievedPage
    return RetrievedPage(
        requested_title=title,
        title=title,
        wiki_page_id=wiki_page_id,
        canonical_url=url or "",
        revision_id=1,
        revision_timestamp=datetime.now(timezone.utc),
        sha1="abc",
        wikitext=wikitext,
    )


def test_export_requires_source_url(tmp_path):
    wikitext = load_fixture("shibuya.wiki")
    retrieved = _retrieved("Tokyo/Shibuya", 36260, wikitext, None)
    extracted = extract_page(retrieved.title, wikitext)
    with pytest.raises(ValueError, match="source_url"):
        export_page_json(retrieved, extracted, data_dir=tmp_path)


def test_export_writes_source_url_on_all_layers(tmp_path):
    wikitext = load_fixture("shibuya.wiki")
    url = "https://en.wikivoyage.org/wiki/Tokyo/Shibuya"
    retrieved = _retrieved("Tokyo/Shibuya", 36260, wikitext, url)
    extracted = extract_page(retrieved.title, wikitext)
    paths = export_page_json(retrieved, extracted, data_dir=tmp_path)

    import json

    raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
    structured = json.loads(paths["structured"].read_text(encoding="utf-8"))
    chunks = json.loads(paths["chunks"].read_text(encoding="utf-8"))

    assert raw["source_url"] == url
    assert structured["source_url"] == url
    assert structured["page"]["canonical_url"] == url
    assert chunks["source_url"] == url
    assert chunks["chunks"]
    assert all(c.get("source_url") == url for c in chunks["chunks"])


def test_validate_rejects_missing_canonical_url():
    wikitext = load_fixture("shibuya.wiki")
    extracted = extract_page("Tokyo/Shibuya", wikitext)
    result = validate_extracted_page("Tokyo/Shibuya", 36260, None, wikitext, extracted)
    assert result.ok is False
    assert any(i.field == "canonical_url" and i.fatal for i in result.issues)
