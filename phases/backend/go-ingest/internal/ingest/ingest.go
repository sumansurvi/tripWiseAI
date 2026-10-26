package ingest

import (
	"fmt"
	"sync"
	"sync/atomic"

	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/chunk"
	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/config"
	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/export"
	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/wikivoyage"
)

type Result struct {
	Succeeded int64
	Failed    int64
	Skipped   int64
}

type job struct {
	title string
	depth int
}

func Run(cfg config.Config) (Result, error) {
	client := wikivoyage.NewClient(cfg.APIURL, cfg.UserAgent, cfg.TimeoutSec, cfg.MaxRetries, cfg.DelaySec)

	var (
		mu      sync.Mutex
		seen    = map[string]struct{}{}
		pending int
		res     Result
		wg      sync.WaitGroup
		logMu   sync.Mutex
	)
	jobs := make(chan job, 256)

	progress := func(status, title string, chunks, depth int) {
		logMu.Lock()
		defer logMu.Unlock()
		line := fmt.Sprintf(
			"progress ok=%d fail=%d skip=%d | %s %q chunks=%d depth=%d",
			atomic.LoadInt64(&res.Succeeded),
			atomic.LoadInt64(&res.Failed),
			atomic.LoadInt64(&res.Skipped),
			status,
			title,
			chunks,
			depth,
		)
		// Overwrite one terminal line; pad so shorter updates clear leftovers.
		fmt.Printf("\r%-120s", line)
	}

	tryEnqueue := func(title string, depth int) {
		key := normalizeKey(title)
		if key == "" {
			return
		}
		mu.Lock()
		defer mu.Unlock()
		if _, ok := seen[key]; ok {
			return
		}
		if cfg.MaxPages > 0 && len(seen) >= cfg.MaxPages {
			return
		}
		seen[key] = struct{}{}
		pending++
		wg.Add(1)
		go func(j job) {
			jobs <- j
		}(job{title: title, depth: depth})
	}

	for _, s := range cfg.Seeds {
		tryEnqueue(s, 0)
	}

	worker := func() {
		for j := range jobs {
			func() {
				defer wg.Done()
				page, err := client.Fetch(j.title)
				if err != nil {
					atomic.AddInt64(&res.Failed, 1)
					progress("fail", j.title, 0, j.depth)
					return
				}
				if page.Missing || page.Wikitext == "" {
					atomic.AddInt64(&res.Skipped, 1)
					progress("skip", j.title, 0, j.depth)
					return
				}
				sections := chunk.SplitSections(page.Wikitext)
				chunks := chunk.BuildChunks(page.Title, page.CanonicalURL, page.PageID, page.RevisionID, sections, 40)
				if err := export.WritePage(cfg.DataDir, page, sections, chunks); err != nil {
					atomic.AddInt64(&res.Failed, 1)
					progress("fail", page.Title, 0, j.depth)
					return
				}
				atomic.AddInt64(&res.Succeeded, 1)
				progress("ok", page.Title, len(chunks), j.depth)

				if j.depth < cfg.MaxDepth {
					for _, child := range chunk.DiscoverLinks(page.Wikitext) {
						tryEnqueue(child, j.depth+1)
					}
				}
			}()
		}
	}

	var workersWG sync.WaitGroup
	workersWG.Add(cfg.Workers)
	for i := 0; i < cfg.Workers; i++ {
		go func() {
			defer workersWG.Done()
			worker()
		}()
	}

	wg.Wait()
	close(jobs)
	workersWG.Wait()
	fmt.Print("\n")
	return res, nil
}

func normalizeKey(title string) string {
	out := make([]rune, 0, len(title))
	for _, r := range title {
		if r >= 'A' && r <= 'Z' {
			out = append(out, r+('a'-'A'))
		} else {
			out = append(out, r)
		}
	}
	return string(out)
}
