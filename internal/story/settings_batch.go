package story

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

// BatchImportResult summarizes a batch settings import.
type BatchImportResult struct {
	Added   int      `json:"added"`
	Skipped int      `json:"skipped"`
	Errors  []string `json:"errors,omitempty"`
}

// SettingsBatchImport is the combined import payload for characters, worldview, and organizations.
type SettingsBatchImport struct {
	Characters    []Character      `json:"characters,omitempty"`
	Worldview     []WorldviewEntry `json:"worldview,omitempty"`
	Organizations []Organization   `json:"organizations,omitempty"`
}

// SettingsBatchImportResult aggregates per-section batch results.
type SettingsBatchImportResult struct {
	Characters    BatchImportResult `json:"characters"`
	Worldview     BatchImportResult `json:"worldview"`
	Organizations BatchImportResult `json:"organizations"`
}

// DecodeBatchArray accepts either a JSON array or an object with one of keys / "items".
func DecodeBatchArray[T any](r io.Reader, keys ...string) ([]T, error) {
	raw, err := io.ReadAll(r)
	if err != nil {
		return nil, err
	}
	if len(raw) == 0 {
		return nil, fmt.Errorf("empty body")
	}

	var items []T
	if err := json.Unmarshal(raw, &items); err == nil {
		return items, nil
	}

	var wrap map[string]json.RawMessage
	if err := json.Unmarshal(raw, &wrap); err != nil {
		return nil, fmt.Errorf("expected JSON array or object")
	}
	for _, k := range keys {
		if v, ok := wrap[k]; ok {
			if err := json.Unmarshal(v, &items); err == nil {
				return items, nil
			}
		}
	}
	if v, ok := wrap["items"]; ok {
		if err := json.Unmarshal(v, &items); err == nil {
			return items, nil
		}
	}
	return nil, fmt.Errorf("expected JSON array or object with %v or items", keys)
}

func (ps *ProjectSettings) characterNameIndex() map[string]string {
	m := make(map[string]string)
	for _, c := range ps.Characters {
		name := strings.TrimSpace(StripNameMarks(c.Name))
		if name != "" {
			m[name] = c.ID
		}
	}
	return m
}

func (ps *ProjectSettings) resolveMemberRefs(members []string) ([]string, []string) {
	if len(members) == 0 {
		return nil, nil
	}
	byName := ps.characterNameIndex()
	ids := make([]string, 0, len(members))
	var warnings []string
	seen := make(map[string]bool)
	for _, ref := range members {
		ref = strings.TrimSpace(ref)
		if ref == "" {
			continue
		}
		id := ref
		if !strings.HasPrefix(ref, "c_") {
			if mapped, ok := byName[StripNameMarks(ref)]; ok {
				id = mapped
			} else {
				warnings = append(warnings, fmt.Sprintf("成员 %q 未匹配到角色，已忽略", ref))
				continue
			}
		}
		if seen[id] {
			continue
		}
		seen[id] = true
		ids = append(ids, id)
	}
	return ids, warnings
}

// BatchAddCharacters appends characters; provided id fields are ignored.
func (ps *ProjectSettings) BatchAddCharacters(items []Character) BatchImportResult {
	var res BatchImportResult
	for i, item := range items {
		line := i + 1
		name := strings.TrimSpace(item.Name)
		if name == "" {
			res.Skipped++
			res.Errors = append(res.Errors, fmt.Sprintf("第 %d 条: 名称不能为空", line))
			continue
		}
		item.ID = ps.NextCharacterID()
		item.Name = name
		ps.Characters = append(ps.Characters, item)
		res.Added++
	}
	return res
}

// BatchAddWorldview appends worldview entries; provided id fields are ignored.
func (ps *ProjectSettings) BatchAddWorldview(items []WorldviewEntry) BatchImportResult {
	var res BatchImportResult
	for i, item := range items {
		line := i + 1
		name := strings.TrimSpace(item.Name)
		desc := strings.TrimSpace(item.Description)
		if name == "" || desc == "" {
			res.Skipped++
			res.Errors = append(res.Errors, fmt.Sprintf("第 %d 条: 名称和描述不能为空", line))
			continue
		}
		item.ID = ps.NextWorldviewID()
		item.Name = name
		item.Description = desc
		if strings.TrimSpace(item.Category) == "" {
			item.Category = "other"
		}
		ps.Worldview = append(ps.Worldview, item)
		res.Added++
	}
	return res
}

// BatchAddOrganizations appends organizations; members may be character ids or names.
func (ps *ProjectSettings) BatchAddOrganizations(items []Organization) BatchImportResult {
	var res BatchImportResult
	for i, item := range items {
		line := i + 1
		name := strings.TrimSpace(item.Name)
		if name == "" {
			res.Skipped++
			res.Errors = append(res.Errors, fmt.Sprintf("第 %d 条: 名称不能为空", line))
			continue
		}
		members, warnings := ps.resolveMemberRefs(item.Members)
		for _, w := range warnings {
			res.Errors = append(res.Errors, fmt.Sprintf("第 %d 条: %s", line, w))
		}
		item.ID = ps.NextOrganizationID()
		item.Name = name
		item.Members = members
		ps.Organizations = append(ps.Organizations, item)
		res.Added++
	}
	return res
}

// BatchImportSettings imports all three sections in dependency order.
func (ps *ProjectSettings) BatchImportSettings(payload SettingsBatchImport) SettingsBatchImportResult {
	return SettingsBatchImportResult{
		Characters:    ps.BatchAddCharacters(payload.Characters),
		Worldview:     ps.BatchAddWorldview(payload.Worldview),
		Organizations: ps.BatchAddOrganizations(payload.Organizations),
	}
}

func (r BatchImportResult) TotalProcessed() int {
	return r.Added + r.Skipped
}

func (r SettingsBatchImportResult) TotalAdded() int {
	return r.Characters.Added + r.Worldview.Added + r.Organizations.Added
}
