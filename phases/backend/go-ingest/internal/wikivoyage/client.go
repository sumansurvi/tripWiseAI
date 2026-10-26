package wikivoyage

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Client struct {
	APIURL     string
	UserAgent  string
	HTTP       *http.Client
	MaxRetries int
	Delay      time.Duration
}

type Page struct {
	RequestedTitle string
	Title          string
	PageID         int
	RevisionID     int
	Timestamp      string
	CanonicalURL   string
	Wikitext       string
	Missing        bool
}

func NewClient(apiURL, userAgent string, timeoutSec float64, maxRetries int, delaySec float64) *Client {
	if timeoutSec <= 0 {
		timeoutSec = 45
	}
	return &Client{
		APIURL:     apiURL,
		UserAgent:  userAgent,
		HTTP:       &http.Client{Timeout: time.Duration(timeoutSec * float64(time.Second))},
		MaxRetries: maxRetries,
		Delay:      time.Duration(delaySec * float64(time.Second)),
	}
}

func (c *Client) Fetch(title string) (*Page, error) {
	var lastErr error
	for attempt := 0; attempt <= c.MaxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt) * time.Second)
		}
		if c.Delay > 0 {
			time.Sleep(c.Delay)
		}
		page, err := c.fetchOnce(title)
		if err == nil {
			return page, nil
		}
		lastErr = err
	}
	return nil, lastErr
}

func (c *Client) fetchOnce(title string) (*Page, error) {
	q := url.Values{}
	q.Set("action", "query")
	q.Set("format", "json")
	q.Set("formatversion", "2")
	q.Set("redirects", "1")
	q.Set("prop", "info|revisions")
	q.Set("inprop", "url")
	q.Set("rvprop", "ids|timestamp|content")
	q.Set("rvslots", "main")
	q.Set("titles", title)

	req, err := http.NewRequest(http.MethodGet, c.APIURL+"?"+q.Encode(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", c.UserAgent)
	req.Header.Set("Accept", "application/json")

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500 {
		return nil, fmt.Errorf("wikivoyage HTTP %d", resp.StatusCode)
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("wikivoyage HTTP %d: %s", resp.StatusCode, string(body))
	}

	var parsed struct {
		Query struct {
			Pages []struct {
				Title     string `json:"title"`
				PageID    int    `json:"pageid"`
				Missing   bool   `json:"missing"`
				FullURL   string `json:"fullurl"`
				Revisions []struct {
					Revid     int    `json:"revid"`
					Timestamp string `json:"timestamp"`
					Slots     struct {
						Main struct {
							Content string `json:"content"`
						} `json:"main"`
					} `json:"slots"`
				} `json:"revisions"`
			} `json:"pages"`
		} `json:"query"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, err
	}
	if len(parsed.Query.Pages) == 0 {
		return nil, fmt.Errorf("no pages returned for %q", title)
	}
	p := parsed.Query.Pages[0]
	out := &Page{
		RequestedTitle: title,
		Title:          p.Title,
		PageID:         p.PageID,
		CanonicalURL:   p.FullURL,
		Missing:        p.Missing,
	}
	if out.CanonicalURL == "" && out.Title != "" {
		out.CanonicalURL = "https://en.wikivoyage.org/wiki/" + strings.ReplaceAll(url.PathEscape(out.Title), "%2F", "/")
		out.CanonicalURL = strings.ReplaceAll(out.CanonicalURL, "+", "_")
	}
	if len(p.Revisions) > 0 {
		out.RevisionID = p.Revisions[0].Revid
		out.Timestamp = p.Revisions[0].Timestamp
		out.Wikitext = p.Revisions[0].Slots.Main.Content
	}
	return out, nil
}
