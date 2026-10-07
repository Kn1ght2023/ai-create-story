package config

import (
	"encoding/json"
	"fmt"
	"os"

	"showmethestory/internal/fsutil"
)

// Feature route keys for per-capability API profile binding.
const (
	APIFeatureWriting     = "writing"
	APIFeaturePolish      = "polish"
	APIFeatureOutline     = "outline"
	APIFeatureAgent       = "agent"
	APIFeaturePostprocess = "postprocess"
)

// APIFeatureKeys lists all supported route keys in stable UI order.
var APIFeatureKeys = []string{
	APIFeatureWriting,
	APIFeaturePolish,
	APIFeatureOutline,
	APIFeatureAgent,
	APIFeaturePostprocess,
}

// APIProfile is a named connection preset (key, URL, model, limits).
type APIProfile struct {
	ID                  string `json:"id"`
	Name                string `json:"name"`
	APIKey              string `json:"api_key"`
	BaseURL             string `json:"base_url"`
	URLStrict           bool   `json:"url_strict,omitempty"`
	Model               string `json:"model"`
	MaxTokens           int    `json:"max_tokens,omitempty"`
	HTTPTimeoutSeconds  int    `json:"http_timeout_seconds"`
	ContextBudgetTokens int    `json:"context_budget_tokens"`
}

// APIStore is the on-disk shape of api.json: multiple profiles + feature routes.
type APIStore struct {
	Profiles []APIProfile     `json:"profiles"`
	Routes   map[string]string `json:"routes"`
}

// ToAPIConfig copies connection fields into an APIConfig used by llm callers.
func (p *APIProfile) ToAPIConfig() *APIConfig {
	if p == nil {
		return DefaultAPIConfig()
	}
	cfg := &APIConfig{
		APIKey:              p.APIKey,
		BaseURL:             p.BaseURL,
		URLStrict:           p.URLStrict,
		Model:               p.Model,
		MaxTokens:           p.MaxTokens,
		HTTPTimeoutSeconds:  p.HTTPTimeoutSeconds,
		ContextBudgetTokens: p.ContextBudgetTokens,
	}
	normalizeAPIConfig(cfg)
	return cfg
}

func profileFromAPIConfig(id, name string, cfg *APIConfig) APIProfile {
	if cfg == nil {
		cfg = DefaultAPIConfig()
	}
	normalizeAPIConfig(cfg)
	return APIProfile{
		ID:                  id,
		Name:                name,
		APIKey:              cfg.APIKey,
		BaseURL:             cfg.BaseURL,
		URLStrict:           cfg.URLStrict,
		Model:               cfg.Model,
		MaxTokens:           cfg.MaxTokens,
		HTTPTimeoutSeconds:  cfg.HTTPTimeoutSeconds,
		ContextBudgetTokens: cfg.ContextBudgetTokens,
	}
}

func normalizeAPIConfig(cfg *APIConfig) {
	if cfg == nil {
		return
	}
	if cfg.HTTPTimeoutSeconds <= 0 {
		cfg.HTTPTimeoutSeconds = DefaultHTTPTimeoutSeconds
	}
}

func normalizeAPIProfile(p *APIProfile) {
	if p == nil {
		return
	}
	if p.HTTPTimeoutSeconds <= 0 {
		p.HTTPTimeoutSeconds = DefaultHTTPTimeoutSeconds
	}
}

// DefaultAPIStore returns a single empty "default" profile with all routes pointing to it.
func DefaultAPIStore() *APIStore {
	p := profileFromAPIConfig("default", "默认", DefaultAPIConfig())
	return &APIStore{
		Profiles: []APIProfile{p},
		Routes:   defaultRoutes(p.ID),
	}
}

func defaultRoutes(profileID string) map[string]string {
	r := make(map[string]string, len(APIFeatureKeys))
	for _, k := range APIFeatureKeys {
		r[k] = profileID
	}
	return r
}

// Normalize fills missing routes, timeouts, and ensures at least one profile.
func (s *APIStore) Normalize() {
	if s == nil {
		return
	}
	if len(s.Profiles) == 0 {
		*s = *DefaultAPIStore()
		return
	}
	for i := range s.Profiles {
		normalizeAPIProfile(&s.Profiles[i])
		if s.Profiles[i].ID == "" {
			s.Profiles[i].ID = fmt.Sprintf("profile-%d", i+1)
		}
		if s.Profiles[i].Name == "" {
			s.Profiles[i].Name = s.Profiles[i].ID
		}
	}
	if s.Routes == nil {
		s.Routes = make(map[string]string)
	}
	fallback := s.Profiles[0].ID
	if id, ok := s.Routes[APIFeatureWriting]; ok && id != "" && s.profileIndex(id) >= 0 {
		fallback = id
	}
	for _, k := range APIFeatureKeys {
		id := s.Routes[k]
		if id == "" || s.profileIndex(id) < 0 {
			s.Routes[k] = fallback
		}
	}
}

func (s *APIStore) profileIndex(id string) int {
	if s == nil {
		return -1
	}
	for i := range s.Profiles {
		if s.Profiles[i].ID == id {
			return i
		}
	}
	return -1
}

// ProfileByID returns a profile pointer or nil.
func (s *APIStore) ProfileByID(id string) *APIProfile {
	i := s.profileIndex(id)
	if i < 0 {
		return nil
	}
	return &s.Profiles[i]
}

// Resolve returns the APIConfig for a feature route.
// Missing route falls back to writing, then the first profile.
func (s *APIStore) Resolve(feature string) (*APIConfig, error) {
	if s == nil || len(s.Profiles) == 0 {
		return nil, fmt.Errorf("API 配置为空")
	}
	s.Normalize()

	tryIDs := []string{}
	if feature != "" {
		if id := s.Routes[feature]; id != "" {
			tryIDs = append(tryIDs, id)
		}
	}
	if feature != APIFeatureWriting {
		if id := s.Routes[APIFeatureWriting]; id != "" {
			tryIDs = append(tryIDs, id)
		}
	}
	tryIDs = append(tryIDs, s.Profiles[0].ID)

	seen := map[string]bool{}
	for _, id := range tryIDs {
		if id == "" || seen[id] {
			continue
		}
		seen[id] = true
		if p := s.ProfileByID(id); p != nil {
			return p.ToAPIConfig(), nil
		}
	}
	return s.Profiles[0].ToAPIConfig(), nil
}

// MustResolve is Resolve that never returns nil (uses DefaultAPIConfig on hard failure).
func (s *APIStore) MustResolve(feature string) *APIConfig {
	cfg, err := s.Resolve(feature)
	if err != nil || cfg == nil {
		return DefaultAPIConfig()
	}
	return cfg
}

// LoadAPIStore loads api.json. Legacy single-object files are migrated in memory
// (and rewritten to the multi-profile format when possible).
func LoadAPIStore(path string) (*APIStore, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			store := DefaultAPIStore()
			if saveErr := SaveAPIStore(path, store); saveErr != nil {
				return nil, fmt.Errorf("创建默认API配置文件失败: %w", saveErr)
			}
			return store, nil
		}
		return nil, fmt.Errorf("读取API配置文件失败: %w", err)
	}

	store, migrated, err := parseAPIStoreJSON(data)
	if err != nil {
		return nil, fmt.Errorf("解析API配置文件失败: %w", err)
	}
	store.Normalize()

	if migrated {
		_ = SaveAPIStore(path, store)
	}
	return store, nil
}

// parseAPIStoreJSON accepts either the multi-profile store or a legacy APIConfig object.
func parseAPIStoreJSON(data []byte) (*APIStore, bool, error) {
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(data, &probe); err != nil {
		return nil, false, err
	}

	if _, hasProfiles := probe["profiles"]; hasProfiles {
		var store APIStore
		if err := json.Unmarshal(data, &store); err != nil {
			return nil, false, err
		}
		return &store, false, nil
	}

	// Legacy flat APIConfig
	var cfg APIConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, false, err
	}
	normalizeAPIConfig(&cfg)
	p := profileFromAPIConfig("default", "默认", &cfg)
	store := &APIStore{
		Profiles: []APIProfile{p},
		Routes:   defaultRoutes(p.ID),
	}
	return store, true, nil
}

// SaveAPIStore writes the multi-profile api.json.
func SaveAPIStore(path string, store *APIStore) error {
	if store == nil {
		store = DefaultAPIStore()
	}
	store.Normalize()
	data, err := json.MarshalIndent(store, "", "  ")
	if err != nil {
		return err
	}
	return fsutil.WriteFileAtomic(path, data)
}

// LoadAPIConfig loads api.json and returns the writing-route profile for callers
// that only need a single connection (startup blank-check, etc.).
func LoadAPIConfig(path string) (*APIConfig, error) {
	store, err := LoadAPIStore(path)
	if err != nil {
		return nil, err
	}
	return store.MustResolve(APIFeatureWriting), nil
}

func saveAPIConfig(path string, cfg *APIConfig) error {
	store := &APIStore{
		Profiles: []APIProfile{profileFromAPIConfig("default", "默认", cfg)},
		Routes:   defaultRoutes("default"),
	}
	return SaveAPIStore(path, store)
}
