package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

type Config struct {
	RepoRoot    string
	DataDir     string
	APIURL      string
	UserAgent   string
	Seeds       []string
	MaxDepth    int
	MaxPages    int
	Workers     int
	DelaySec    float64
	MaxRetries  int
	TimeoutSec  float64
	ScopeMode   string
	ScopeRoot   string
}

func FindRepoRoot() string {
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	dir := wd
	for {
		if fileExists(filepath.Join(dir, "config")) && fileExists(filepath.Join(dir, "docs")) {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return wd
}

func Load(dataDirFlag string, maxPagesFlag int, workersFlag int, seedsFlag string) (Config, error) {
	root := FindRepoRoot()
	_ = godotenv.Load(filepath.Join(root, "config", ".env"))
	_ = godotenv.Load(filepath.Join(root, ".env"))

	dataDir := dataDirFlag
	if dataDir == "" {
		dataDir = filepath.Join(root, "data")
	} else if !filepath.IsAbs(dataDir) {
		dataDir = filepath.Join(root, dataDir)
	}

	seeds := splitCSV(seedsFlag)
	if len(seeds) == 0 {
		seeds = splitCSV(os.Getenv("TRIPWISE_SEEDS"))
	}
	if len(seeds) == 0 {
		seeds = []string{"India", "Delhi", "Mumbai", "Jaipur", "Agra", "Varanasi", "Goa"}
	}

	cfg := Config{
		RepoRoot:   root,
		DataDir:    dataDir,
		APIURL:     envOr("WIKIVOYAGE_API_URL", "https://en.wikivoyage.org/w/api.php"),
		UserAgent:  envOr("WIKIVOYAGE_USER_AGENT", "TripWiseAI/0.1 (go-ingest; travel-research portfolio)"),
		Seeds:      seeds,
		MaxDepth:   envInt("TRIPWISE_MAX_DEPTH", 1),
		MaxPages:   envInt("TRIPWISE_MAX_PAGES", 0),
		Workers:    envInt("TRIPWISE_BATCH_SIZE", 8),
		DelaySec:   envFloat("TRIPWISE_REQUEST_DELAY_SECONDS", 0.35),
		MaxRetries: envInt("TRIPWISE_MAX_RETRIES", 4),
		TimeoutSec: envFloat("TRIPWISE_TIMEOUT_SECONDS", 45),
		ScopeMode:  envOr("TRIPWISE_SCOPE_MODE", "seeds_and_districts"),
		ScopeRoot:  envOr("TRIPWISE_SCOPE_ROOT", "India"),
	}
	if maxPagesFlag > 0 {
		cfg.MaxPages = maxPagesFlag
	}
	if workersFlag > 0 {
		cfg.Workers = workersFlag
	}
	if cfg.Workers < 1 {
		cfg.Workers = 1
	}
	if cfg.Workers > 16 {
		cfg.Workers = 16
	}
	return cfg, nil
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func envOr(k, def string) string {
	if v := strings.TrimSpace(os.Getenv(k)); v != "" {
		return v
	}
	return def
}

func envInt(k string, def int) int {
	v := strings.TrimSpace(os.Getenv(k))
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func envFloat(k string, def float64) float64 {
	v := strings.TrimSpace(os.Getenv(k))
	if v == "" {
		return def
	}
	n, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return def
	}
	return n
}

func splitCSV(s string) []string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
