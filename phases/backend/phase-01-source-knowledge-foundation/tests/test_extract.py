from tripwise.classify import classify_page, extract_geo, extract_is_part_of
from tripwise.cleaning import sha256_text, strip_wikitext
from tripwise.discovery import maybe_enqueue_children, seed_queue
from tripwise.extract import extract_page
from tripwise.validate import validate_extracted_page

from fixtures_util import load_fixture


def test_classify_district_from_status_template():
    result = classify_page("Tokyo/Shibuya", load_fixture("shibuya.wiki"))
    assert result.page_type == "district"
    assert result.article_status == "usable"
    assert result.is_huge_city is False


def test_classify_huge_city_from_print_districts():
    result = classify_page("Tokyo", load_fixture("tokyo.wiki"))
    assert result.page_type == "city"
    assert result.article_status == "guide"
    assert result.is_huge_city is True


def test_classify_country():
    result = classify_page("Japan", load_fixture("japan.wiki"))
    assert result.page_type == "country"
    assert extract_is_part_of(load_fixture("japan.wiki")) == "East Asia"


def test_geo_extracted_not_invented():
    lat, lon = extract_geo(load_fixture("shibuya.wiki"))
    assert round(lat, 3) == 35.664
    assert round(lon, 3) == 139.698


def test_section_hierarchy_preserved():
    extracted = extract_page("Tokyo/Shibuya", load_fixture("shibuya.wiki"))
    paths = {s.heading_path for s in extracted.sections}
    assert "Lead" in paths
    assert "Lead > Understand" in paths
    assert "Lead > Understand > Climate" in paths
    assert "Lead > Sleep" in paths
    sleep = next(s for s in extracted.sections if s.heading_path == "Lead > Sleep")
    assert "lively" not in sleep.cleaned_text.lower() or "nightlife" in sleep.cleaned_text.lower()
    assert "convenient if you want nightlife" in sleep.cleaned_text


def test_rich_text_not_flattened_to_booleans():
    extracted = extract_page("Tokyo/Shibuya", load_fixture("shibuya.wiki"))
    understand = next(s for s in extracted.sections if s.section_title == "Understand" and s.subsection_title is None)
    assert "particularly lively in the evening" in understand.cleaned_text
    assert "inexpensive restaurants" in understand.cleaned_text


def test_listing_extraction():
    extracted = extract_page("Tokyo/Shibuya", load_fixture("shibuya.wiki"))
    kinds = {lst.listing_kind for lst in extracted.listings}
    assert kinds == {"see", "do", "buy", "eat", "drink", "sleep"}
    crossing = next(lst for lst in extracted.listings if lst.name == "Shibuya Crossing")
    assert crossing.latitude == 35.6595
    assert crossing.price_raw == "Free"
    assert "busiest pedestrian intersections" in crossing.description


def test_relationship_extraction():
    extracted = extract_page("Tokyo", load_fixture("tokyo.wiki"))
    rels = {(r.to_title, r.relationship_type) for r in extracted.relationships}
    assert ("Tokyo (prefecture)", "is_part_of") in rels
    assert ("Tokyo/Shibuya", "district_child") in rels
    assert ("Tokyo/Shinjuku", "district_child") in rels
    assert ("Kyoto", "go_next") in rels


def test_district_child_requires_subpage_prefix():
    wikitext = load_fixture("tokyo.wiki") + "\n* [[Yokohama]]\n* [[Tokyo#Get around]]\n"
    extracted = extract_page("Tokyo", wikitext)
    rels = {r.to_title for r in extracted.relationships if r.relationship_type == "district_child"}
    assert "Yokohama" not in rels
    assert "Tokyo/Shibuya" in rels
    assert all(not t.startswith("#") for t in rels)


def test_cleaning_does_not_summarize():
    raw = "This district is particularly lively in the evening and is known for its inexpensive restaurants."
    cleaned = strip_wikitext(raw)
    assert cleaned == raw


def test_normalize_hash_stable():
    text = load_fixture("shibuya.wiki")
    assert sha256_text(text) == sha256_text(text)


def test_validation_accepts_complete_page():
    wikitext = load_fixture("shibuya.wiki")
    extracted = extract_page("Tokyo/Shibuya", wikitext)
    result = validate_extracted_page(
        "Tokyo/Shibuya",
        36260,
        "https://en.wikivoyage.org/wiki/Tokyo/Shibuya",
        wikitext,
        extracted,
    )
    assert result.ok is True


def test_validation_rejects_missing_id():
    wikitext = load_fixture("shibuya.wiki")
    extracted = extract_page("Tokyo/Shibuya", wikitext)
    result = validate_extracted_page("Tokyo/Shibuya", None, "https://en.wikivoyage.org/wiki/Tokyo/Shibuya", wikitext, extracted)
    assert result.ok is False


def test_discovery_districts_only_by_default():
    extracted = extract_page("Tokyo", load_fixture("tokyo.wiki"))
    state = seed_queue(["Tokyo"])
    added = maybe_enqueue_children(
        state,
        extracted,
        current_depth=0,
        max_depth=1,
        follow_go_next=False,
        scope_mode="seeds_and_districts",
        allowed_page_types=["city", "district"],
    )
    assert added == 2
    queued_titles = {item.title for item in state.queued}
    assert "Tokyo/Shibuya" in queued_titles
    assert "Kyoto" not in queued_titles


def test_discovery_scope_root_follows_district_children():
    extracted = extract_page("Tokyo", load_fixture("tokyo.wiki"))
    state = seed_queue(["Tokyo"])
    added = maybe_enqueue_children(
        state,
        extracted,
        current_depth=0,
        max_depth=12,
        follow_go_next=False,
        scope_mode="scope_root",
        allowed_page_types=["city", "district", "region", "country"],
    )
    assert added >= 2
    queued_titles = {item.title for item in state.queued}
    assert "Tokyo/Shibuya" in queued_titles
    assert "Tokyo/Shinjuku" in queued_titles


def test_discovery_respects_max_depth():
    extracted = extract_page("Tokyo", load_fixture("tokyo.wiki"))
    state = seed_queue(["Tokyo"])
    added = maybe_enqueue_children(
        state,
        extracted,
        current_depth=1,
        max_depth=1,
        follow_go_next=False,
        scope_mode="seeds_and_districts",
        allowed_page_types=["city", "district"],
    )
    assert added == 0
