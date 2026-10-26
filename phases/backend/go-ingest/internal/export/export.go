package export

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/chunk"
	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/wikivoyage"
)

const (
	licenseName = "CC BY-SA 4.0"
	licenseURL  = "https://creativecommons.org/licenses/by-sa/4.0/"
	sourceID    = "wikivoyage-en"
	sourceHome  = "https://en.wikivoyage.org/"
)

func WritePage(dataDir string, page *wikivoyage.Page, sections []chunk.Section, chunks []chunk.Chunk) error {
	if page == nil || strings.TrimSpace(page.CanonicalURL) == "" {
		title := ""
		if page != nil {
			title = page.Title
		}
		return fmt.Errorf("missing canonical_url for %q", title)
	}
	slug := chunk.TitleSlug(page.Title)
	attr := fmt.Sprintf(
		"Text from English Wikivoyage article '%s' (%s), licensed under CC BY-SA 4.0.",
		page.Title,
		historyURL(page.Title, page.RevisionID),
	)
	source := map[string]string{
		"id":           sourceID,
		"name":         "English Wikivoyage",
		"base_url":     sourceHome,
		"license_name": licenseName,
		"license_url":  licenseURL,
	}

	raw := map[string]any{
		"source_url":         page.CanonicalURL,
		"title":              page.Title,
		"requested_title":    page.RequestedTitle,
		"wiki_page_id":       page.PageID,
		"revision_id":        page.RevisionID,
		"revision_timestamp": page.Timestamp,
		"license":            licenseName,
		"attribution":        attr,
		"source":             source,
		"wikitext":           page.Wikitext,
		"ingested_by":        "go-ingest",
	}

	secPayload := make([]map[string]any, 0, len(sections))
	for _, s := range sections {
		secPayload = append(secPayload, map[string]any{
			"heading_path":     s.HeadingPath,
			"section_title":    s.SectionTitle,
			"subsection_title": s.SubsectionTitle,
			"heading_level":    s.Level,
			"cleaned_text":     s.Text,
			"source_url":       page.CanonicalURL,
		})
	}
	structured := map[string]any{
		"source_url":   page.CanonicalURL,
		"title":        page.Title,
		"wiki_page_id": page.PageID,
		"revision_id":  page.RevisionID,
		"license":      licenseName,
		"attribution":  attr,
		"source":       source,
		"page": map[string]any{
			"wiki_page_id":       page.PageID,
			"title":              page.Title,
			"canonical_url":      page.CanonicalURL,
			"page_type":          "unknown",
			"revision_id":        page.RevisionID,
			"revision_timestamp": page.Timestamp,
			"license":            licenseName,
			"attribution":        attr,
		},
		"sections":    secPayload,
		"listings":    []any{},
		"ingested_by": "go-ingest",
	}

	chunksPayload := map[string]any{
		"source_url":   page.CanonicalURL,
		"title":        page.Title,
		"wiki_page_id": page.PageID,
		"revision_id":  page.RevisionID,
		"license":      licenseName,
		"attribution":  attr,
		"source":       source,
		"chunk_count":  len(chunks),
		"chunks":       chunks,
		"ingested_by":  "go-ingest",
	}

	if err := writeJSON(filepath.Join(dataDir, "raw", slug+".json"), raw); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(dataDir, "structured", slug+".json"), structured); err != nil {
		return err
	}
	return writeJSON(filepath.Join(dataDir, "chunks", slug+".json"), chunksPayload)
}

func writeJSON(path string, payload any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func historyURL(title string, rev int) string {
	safe := strings.ReplaceAll(title, " ", "_")
	if rev > 0 {
		return fmt.Sprintf("https://en.wikivoyage.org/w/index.php?title=%s&oldid=%d", safe, rev)
	}
	return "https://en.wikivoyage.org/wiki/" + safe
}
