package story

import (
	"showmethestory/internal/i18n"
	"strings"
	"testing"
)

func TestAssignArcRanges(t *testing.T) {
	// Exact total: ranges are contiguous starting at 1.
	r := assignArcRanges([]int{10, 20, 30}, 1, 60)
	if r[0].Start != 1 || r[0].End != 10 || r[1].Start != 11 || r[1].End != 30 || r[2].Start != 31 || r[2].End != 60 {
		t.Fatalf("exact ranges wrong: %+v", r)
	}
	// Drift: last arc absorbs the difference to hit the exact total.
	r = assignArcRanges([]int{10, 10}, 1, 30)
	if r[1].End != 30 {
		t.Fatalf("drift not absorbed: %+v", r)
	}
	r = assignArcRanges([]int{20, 20}, 1, 30)
	if r[1].End != 30 {
		t.Fatalf("over-count not clamped: %+v", r)
	}
	// Zero counts get a minimum of 1.
	r = assignArcRanges([]int{0, 5}, 5, 10)
	if r[0].Start != 5 || r[0].End != 5 || r[1].End != 14 {
		t.Fatalf("zero count handling wrong: %+v", r)
	}
}

func TestArcLookupAndStatus(t *testing.T) {
	state := &Progress{
		Arcs: []Arc{
			{ID: 1, Title: "A", StartCh: 1, EndCh: 2},
			{ID: 2, Title: "B", StartCh: 3, EndCh: 4},
		},
		Chapters: []ChapterState{
			{Num: 1, Status: StatusAccepted, Summary: "s1"},
			{Num: 2, Status: StatusAccepted, Summary: "s2"},
			{Num: 3, Status: StatusPending},
		},
	}
	if arc := arcForChapterNum(state, 3); arc == nil || arc.ID != 2 {
		t.Fatalf("arcForChapterNum wrong: %+v", arc)
	}
	if arcForChapterNum(state, 99) != nil {
		t.Fatal("expected nil for out-of-range chapter")
	}
	if !arcCompleted(state, &state.Arcs[0]) {
		t.Fatal("arc 1 should be completed")
	}
	if arcCompleted(state, &state.Arcs[1]) {
		t.Fatal("arc 2 has a missing chapter, not completed")
	}
}

func TestBuildPreviousArcContext(t *testing.T) {
	state := &Progress{
		Arcs: []Arc{
			{ID: 1, Title: "开端", StartCh: 1, EndCh: 2, Summary: "卷一摘要"},
			{ID: 2, Title: "发展", StartCh: 3, EndCh: 4},
		},
		Chapters: []ChapterState{
			{Num: 1, Summary: "ch1"},
			{Num: 2, Summary: "ch2"},
		},
	}
	got := buildPreviousArcContext(state, 3, i18n.LangZH)
	if !strings.Contains(got, "卷一摘要") {
		t.Fatalf("missing arc summary: %s", got)
	}
	if !strings.Contains(got, "ch2") {
		t.Fatalf("missing tail chapter summary: %s", got)
	}
	// Opening of the book: fixed placeholder.
	empty := buildPreviousArcContext(&Progress{}, 1, i18n.LangZH)
	if !strings.Contains(empty, "故事开端") {
		t.Fatalf("opening placeholder missing: %s", empty)
	}
}

func TestOutlineConstraintsArcCompression(t *testing.T) {
	state := &Progress{
		Arcs: []Arc{{ID: 1, Title: "开端", StartCh: 1, EndCh: 2, Summary: "卷一摘要"}},
		Chapters: []ChapterState{
			{Num: 1, Title: "一", Outline: "大纲一"},
			{Num: 2, Title: "二", Outline: "大纲二"},
			{Num: 3, Title: "三", Outline: "大纲三"},
			{Num: 4, Title: "四", Outline: "大纲四"},
		},
	}
	got := buildOutlineConstraintsForLang(state, 3, i18n.LangZH) // writing chapter 4
	if !strings.Contains(got, "卷一摘要") {
		t.Fatalf("summarized arc not compressed: %s", got)
	}
	if strings.Contains(got, "大纲一") || strings.Contains(got, "大纲二") {
		t.Fatalf("per-chapter outlines should be replaced by arc summary: %s", got)
	}
	if !strings.Contains(got, "大纲三") {
		t.Fatalf("chapter outside summarized arc must keep its outline: %s", got)
	}
}

func TestTargetChapterNumsForArc(t *testing.T) {
	arc := Arc{StartCh: 1, EndCh: 5}
	state := &Progress{
		Chapters: []ChapterState{
			{Num: 1, Outline: "a"},
			{Num: 2, Outline: "b"},
			{Num: 3, Outline: ""},
			{Num: 4, Outline: "d"},
		},
	}
	full := targetChapterNumsForArc(state, &arc, ArcOutlineModeFull)
	if len(full) != 5 || full[0] != 1 || full[4] != 5 {
		t.Fatalf("full mode nums = %v", full)
	}
	missing := targetChapterNumsForArc(state, &arc, ArcOutlineModeMissing)
	wantMissing := []int{3, 5}
	if len(missing) != len(wantMissing) {
		t.Fatalf("missing mode nums = %v, want %v", missing, wantMissing)
	}
	for i, n := range wantMissing {
		if missing[i] != n {
			t.Fatalf("missing[%d] = %d, want %d", i, missing[i], n)
		}
	}
}

func TestSplitNumsIntoBatches(t *testing.T) {
	nums := []int{19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30}
	batches := splitNumsIntoBatches(nums, 10)
	if len(batches) != 2 || len(batches[0]) != 10 || len(batches[1]) != 2 {
		t.Fatalf("batches = %v", batches)
	}
	if batches[0][0] != 19 || batches[1][1] != 30 {
		t.Fatalf("batch bounds wrong: %v", batches)
	}
}

func TestBuildExistingArcOutlineContext(t *testing.T) {
	arc := Arc{StartCh: 1, EndCh: 30}
	state := &Progress{
		Chapters: []ChapterState{
			{Num: 1, Title: "开", Outline: "第一章情节", Characters: []OutlineChapterCharacter{{Name: "甲"}}},
			{Num: 18, Title: "末", Outline: "第十八章钩子"},
		},
	}
	got := buildExistingArcOutlineContext(state, &arc, 19, i18n.LangZH)
	if !strings.Contains(got, "已有章纲") {
		t.Fatalf("missing header: %s", got)
	}
	if !strings.Contains(got, "第十八章钩子") || !strings.Contains(got, "第一章情节") {
		t.Fatalf("missing chapter outlines: %s", got)
	}
	if strings.Contains(got, "第十九") {
		t.Fatal("should not include chapter 19+")
	}
}

func TestMergeOutlineChaptersIntoState(t *testing.T) {
	state := &Progress{
		Chapters: []ChapterState{
			{Num: 1, Title: "旧1", Outline: "保留", Status: StatusPending},
			{Num: 2, Title: "旧2", Outline: "将被替换", Status: StatusPending},
		},
	}
	mergeOutlineChaptersIntoState(state, []OutlineChapter{
		{Num: 2, Title: "新2", Outline: "新大纲"},
		{Num: 3, Title: "新3", Outline: "新增"},
	})
	if len(state.Chapters) != 3 {
		t.Fatalf("chapters len = %d", len(state.Chapters))
	}
	byNum := map[int]ChapterState{}
	for _, ch := range state.Chapters {
		byNum[ch.Num] = ch
	}
	if byNum[1].Outline != "保留" {
		t.Fatal("chapter 1 should be preserved")
	}
	if byNum[2].Outline != "新大纲" {
		t.Fatal("chapter 2 should be replaced")
	}
	if byNum[3].Title != "新3" {
		t.Fatal("chapter 3 should be added")
	}
}
