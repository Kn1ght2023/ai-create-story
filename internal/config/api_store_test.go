package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestParseAPIStoreJSON_Legacy(t *testing.T) {
	legacy := `{
  "api_key": "sk-test",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "max_tokens": 8192,
  "http_timeout_seconds": 120,
  "context_budget_tokens": 300000
}`
	store, migrated, err := parseAPIStoreJSON([]byte(legacy))
	if err != nil {
		t.Fatal(err)
	}
	if !migrated {
		t.Fatal("expected migrated=true for legacy api.json")
	}
	if len(store.Profiles) != 1 {
		t.Fatalf("profiles=%d", len(store.Profiles))
	}
	if store.Profiles[0].ID != "default" || store.Profiles[0].Model != "deepseek-chat" {
		t.Fatalf("profile=%+v", store.Profiles[0])
	}
	store.Normalize()
	for _, k := range APIFeatureKeys {
		if store.Routes[k] != "default" {
			t.Fatalf("route %s=%q", k, store.Routes[k])
		}
	}
}

func TestParseAPIStoreJSON_Multi(t *testing.T) {
	raw := `{
  "profiles": [
    {"id": "a", "name": "A", "base_url": "https://a.example", "model": "m-a", "http_timeout_seconds": 60},
    {"id": "b", "name": "B", "base_url": "https://b.example", "model": "m-b", "http_timeout_seconds": 60}
  ],
  "routes": {
    "writing": "a",
    "polish": "b"
  }
}`
	store, migrated, err := parseAPIStoreJSON([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	if migrated {
		t.Fatal("expected migrated=false")
	}
	store.Normalize()
	w, err := store.Resolve(APIFeatureWriting)
	if err != nil || w.Model != "m-a" {
		t.Fatalf("writing: %+v err=%v", w, err)
	}
	p, err := store.Resolve(APIFeaturePolish)
	if err != nil || p.Model != "m-b" {
		t.Fatalf("polish: %+v err=%v", p, err)
	}
	// missing outline falls back to writing
	o, err := store.Resolve(APIFeatureOutline)
	if err != nil || o.Model != "m-a" {
		t.Fatalf("outline fallback: %+v err=%v", o, err)
	}
}

func TestResolve_FallbackFirstProfile(t *testing.T) {
	store := &APIStore{
		Profiles: []APIProfile{
			{ID: "only", Name: "Only", Model: "solo", HTTPTimeoutSeconds: 60},
		},
		Routes: map[string]string{
			APIFeatureWriting: "missing-id",
		},
	}
	store.Normalize()
	cfg, err := store.Resolve(APIFeatureWriting)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Model != "solo" {
		t.Fatalf("got model %q", cfg.Model)
	}
}

func TestLoadAPIStore_RoundTripAndMigrate(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "api.json")
	legacy := APIConfig{
		APIKey:             "k",
		BaseURL:            "https://api.example.com",
		Model:              "x",
		HTTPTimeoutSeconds: 90,
	}
	data, _ := json.MarshalIndent(legacy, "", "  ")
	if err := os.WriteFile(path, data, 0644); err != nil {
		t.Fatal(err)
	}

	store, err := LoadAPIStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(store.Profiles) != 1 || store.Profiles[0].Model != "x" {
		t.Fatalf("%+v", store.Profiles)
	}

	// file rewritten as multi-profile
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(raw, &probe); err != nil {
		t.Fatal(err)
	}
	if _, ok := probe["profiles"]; !ok {
		t.Fatalf("expected profiles in rewritten file: %s", raw)
	}

	cfg, err := store.Resolve(APIFeaturePolish)
	if err != nil || cfg.Model != "x" {
		t.Fatalf("%+v %v", cfg, err)
	}
}
