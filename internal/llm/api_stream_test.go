package llm

import (
	"encoding/json"
	"testing"
)

func TestStreamDeltaReasoningContent(t *testing.T) {
	raw := `{"choices":[{"index":0,"delta":{"reasoning_content":"思考"},"finish_reason":null}]}`
	var delta streamDelta
	if err := json.Unmarshal([]byte(raw), &delta); err != nil {
		t.Fatal(err)
	}
	if got := delta.Choices[0].Delta.ReasoningContent; got != "思考" {
		t.Fatalf("ReasoningContent = %q, want 思考", got)
	}
	if delta.Choices[0].Delta.Content != "" {
		t.Fatalf("Content should be empty, got %q", delta.Choices[0].Delta.Content)
	}
}

func TestStreamDeltaContentAndReasoning(t *testing.T) {
	raw := `{"choices":[{"index":0,"delta":{"reasoning_content":"x","content":"y"}}]}`
	var delta streamDelta
	if err := json.Unmarshal([]byte(raw), &delta); err != nil {
		t.Fatal(err)
	}
	if delta.Choices[0].Delta.ReasoningContent != "x" || delta.Choices[0].Delta.Content != "y" {
		t.Fatalf("unexpected delta: %+v", delta.Choices[0].Delta)
	}
}
