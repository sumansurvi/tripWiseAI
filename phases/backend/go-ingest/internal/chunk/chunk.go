package chunk

import (
	"fmt"
	"regexp"
	"strings"
)

var (
	headingRe = regexp.MustCompile(`(?m)^(={2,6})\s*(.+?)\s*={2,6}\s*$`)
	linkRe    = regexp.MustCompile(`\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]`)
	tplRe     = regexp.MustCompile(`(?s)\{\{[^}]*\}\}`)
	refRe     = regexp.MustCompile(`(?s)<ref\b[^>]*>.*?</ref>|<ref\b[^/]*/>`)
	htmlRe    = regexp.MustCompile(`(?s)<[^>]+>`)
	wsRe      = regexp.MustCompile(`[ \t]+\n`)
)

type Section struct {
	HeadingPath     string
	SectionTitle    string
	SubsectionTitle *string
	Level           int
	Text            string
}

type Chunk struct {
	ChunkID         string  `json:"chunk_id"`
	ChunkType       string  `json:"chunk_type"`
	Text            string  `json:"text"`
	HeadingPath     string  `json:"heading_path"`
	SectionTitle    string  `json:"section_title"`
	SubsectionTitle *string `json:"subsection_title"`
	SourceURL       string  `json:"source_url"`
	Title           string  `json:"title"`
	WikiPageID      int     `json:"wiki_page_id"`
	RevisionID      int     `json:"revision_id"`
}

// SplitSections is a lightweight wikitext sectioner (not full mwparser parity).
func SplitSections(wikitext string) []Section {
	matches := headingRe.FindAllStringSubmatchIndex(wikitext, -1)
	type mark struct {
		start, end, level int
		title             string
	}
	marks := make([]mark, 0, len(matches)+1)
	marks = append(marks, mark{start: 0, end: 0, level: 1, title: "Lead"})
	for _, m := range matches {
		eq := wikitext[m[2]:m[3]]
		title := strings.TrimSpace(wikitext[m[4]:m[5]])
		marks = append(marks, mark{start: m[0], end: m[1], level: len(eq), title: title})
	}

	out := make([]Section, 0, len(marks))
	stack := []string{}
	for i, mk := range marks {
		bodyStart := mk.end
		if i == 0 {
			bodyStart = 0
		}
		bodyEnd := len(wikitext)
		if i+1 < len(marks) {
			bodyEnd = marks[i+1].start
		}
		raw := strings.TrimSpace(wikitext[bodyStart:bodyEnd])
		clean := CleanWikitext(raw)
		if i == 0 {
			stack = []string{"Lead"}
		} else {
			for len(stack) >= mk.level {
				stack = stack[:len(stack)-1]
			}
			stack = append(stack, mk.title)
		}
		secTitle := mk.title
		var sub *string
		if len(stack) >= 2 {
			secTitle = stack[len(stack)-2]
			v := stack[len(stack)-1]
			sub = &v
			if i == 0 {
				secTitle = "Lead"
				sub = nil
			}
		}
		if i == 0 {
			secTitle = "Lead"
			sub = nil
		}
		out = append(out, Section{
			HeadingPath:     strings.Join(stack, " > "),
			SectionTitle:    secTitle,
			SubsectionTitle: sub,
			Level:           mk.level,
			Text:            clean,
		})
	}
	return out
}

func CleanWikitext(s string) string {
	s = refRe.ReplaceAllString(s, "")
	s = tplRe.ReplaceAllString(s, "")
	s = htmlRe.ReplaceAllString(s, "")
	s = strings.ReplaceAll(s, "'''", "")
	s = strings.ReplaceAll(s, "''", "")
	s = linkRe.ReplaceAllStringFunc(s, func(m string) string {
		inner := linkRe.FindStringSubmatch(m)
		if len(inner) < 2 {
			return ""
		}
		return strings.TrimSpace(inner[1])
	})
	s = wsRe.ReplaceAllString(s, "\n")
	s = strings.TrimSpace(s)
	return s
}

func BuildChunks(title, sourceURL string, pageID, revID int, sections []Section, minChars int) []Chunk {
	if minChars <= 0 {
		minChars = 40
	}
	slug := TitleSlug(title)
	out := make([]Chunk, 0, len(sections))
	idx := 0
	for _, sec := range sections {
		text := strings.TrimSpace(sec.Text)
		if len(text) < minChars {
			continue
		}
		out = append(out, Chunk{
			ChunkID:         fmt.Sprintf("%s__section__%04d", slug, idx),
			ChunkType:       "section",
			Text:            text,
			HeadingPath:     sec.HeadingPath,
			SectionTitle:    sec.SectionTitle,
			SubsectionTitle: sec.SubsectionTitle,
			SourceURL:       sourceURL,
			Title:           title,
			WikiPageID:      pageID,
			RevisionID:      revID,
		})
		idx++
	}
	return out
}

func DiscoverLinks(wikitext string) []string {
	seen := map[string]struct{}{}
	out := []string{}
	for _, m := range linkRe.FindAllStringSubmatch(wikitext, -1) {
		if len(m) < 2 {
			continue
		}
		t := strings.TrimSpace(m[1])
		if t == "" || strings.Contains(t, ":") {
			continue
		}
		low := strings.ToLower(t)
		if strings.Contains(low, "phrasebook") || strings.Contains(low, "itinerary") {
			continue
		}
		if _, ok := seen[strings.ToLower(t)]; ok {
			continue
		}
		seen[strings.ToLower(t)] = struct{}{}
		out = append(out, t)
	}
	return out
}

func TitleSlug(title string) string {
	t := strings.ReplaceAll(strings.TrimSpace(title), "/", "__")
	var b strings.Builder
	for _, r := range t {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_' || r == '.' || r == '-' {
			b.WriteRune(r)
		} else {
			b.WriteByte('_')
		}
	}
	s := b.String()
	if s == "" {
		return "page"
	}
	return s
}
