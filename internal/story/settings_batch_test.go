package story

import (
	"strings"
	"testing"
)

func TestDecodeBatchArrayFlexible(t *testing.T) {
	raw := `[{"name":"A","description":"d"}]`
	items, err := DecodeBatchArray[WorldviewEntry](strings.NewReader(raw), "worldview")
	if err != nil || len(items) != 1 || items[0].Name != "A" {
		t.Fatalf("array decode failed: %+v err=%v", items, err)
	}

	wrapped := `{"characters":[{"name":"Bob"}]}`
	chars, err := DecodeBatchArray[Character](strings.NewReader(wrapped), "characters")
	if err != nil || len(chars) != 1 || chars[0].Name != "Bob" {
		t.Fatalf("wrapped decode failed: %+v err=%v", chars, err)
	}
}

func TestBatchAddCharactersAndOrgMembersByName(t *testing.T) {
	ps := &ProjectSettings{}
	cr := ps.BatchAddCharacters([]Character{{Name: "林平之", Personality: "谨慎"}})
	if cr.Added != 1 || len(ps.Characters) != 1 {
		t.Fatalf("character batch: %+v", cr)
	}

	or := ps.BatchAddOrganizations([]Organization{
		{Name: "华山派", Type: "宗门", Members: []string{"林平之", "missing"}},
	})
	if or.Added != 1 {
		t.Fatalf("org batch: %+v", or)
	}
	if len(ps.Organizations[0].Members) != 1 || ps.Organizations[0].Members[0] != ps.Characters[0].ID {
		t.Fatalf("members not resolved: %+v", ps.Organizations[0].Members)
	}
	if len(or.Errors) != 1 {
		t.Fatalf("expected member warning, got %+v", or.Errors)
	}
}

func TestBatchAddWorldviewValidation(t *testing.T) {
	ps := &ProjectSettings{}
	res := ps.BatchAddWorldview([]WorldviewEntry{
		{Name: "OK", Description: "desc", Category: "geography"},
		{Name: "bad", Description: ""},
	})
	if res.Added != 1 || res.Skipped != 1 {
		t.Fatalf("unexpected counts: %+v", res)
	}
}
