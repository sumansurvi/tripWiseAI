package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/config"
	"github.com/sumansurvi/tripWiseAI/phases/backend/go-ingest/internal/ingest"
)

func main() {
	maxPages := flag.Int("max-pages", 0, "cap pages this run (0 = use TRIPWISE_MAX_PAGES / unlimited)")
	workers := flag.Int("workers", 0, "concurrent fetch workers")
	seeds := flag.String("seeds", "", "comma-separated seed titles (overrides TRIPWISE_SEEDS)")
	dataDir := flag.String("data-dir", "", "output data directory (default: <repo>/data)")
	flag.Parse()

	cfg, err := config.Load(*dataDir, *maxPages, *workers, *seeds)
	if err != nil {
		fmt.Fprintf(os.Stderr, "config: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("TripWise Go ingest  workers=%d max_pages=%d data=%s seeds=%v\n",
		cfg.Workers, cfg.MaxPages, cfg.DataDir, cfg.Seeds)

	res, err := ingest.Run(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "ingest failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("done succeeded=%d failed=%d skipped=%d\n", res.Succeeded, res.Failed, res.Skipped)
	if res.Succeeded == 0 {
		os.Exit(2)
	}
}
