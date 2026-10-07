"""Shared types for fingerprint MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunConfig:
    run_id: str
    provider_name: str
    base_url: str
    api_key: str
    model: str
    claimed_family: str = "claude"
    timeout_seconds: int = 180
    mode: str = "standard"  # quick | standard | deep
    temperature: float = 0.0
    max_tokens: int = 4096
    enable_long_context: bool = True
    enable_stream: bool = True
    repeats: int = 3
    out_dir: str = ""


@dataclass
class CallMeta:
    http_status: int = 0
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    response_model: str = ""
    response_id: str = ""
    finish_reason: str = ""
    system_fingerprint: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""
    streamed: bool = False
    chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_status": self.http_status,
            "latency_ms": round(self.latency_ms, 1),
            "ttft_ms": None if self.ttft_ms is None else round(self.ttft_ms, 1),
            "response_model": self.response_model,
            "response_id": self.response_id,
            "finish_reason": self.finish_reason,
            "system_fingerprint": self.system_fingerprint,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "headers": {k: v for k, v in self.headers.items() if k.lower() not in {"authorization"}},
            "error": self.error,
            "streamed": self.streamed,
            "chunk_count": self.chunk_count,
        }


@dataclass
class TestResult:
    test_id: str
    name: str
    category: str
    score: float  # 0..1
    weight: float
    status: str  # pass | fail | warn | error | skip
    summary: str
    flags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    raw_responses: list[Any] = field(default_factory=list)
    metas: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "category": self.category,
            "score": round(self.score, 4),
            "weight": self.weight,
            "status": self.status,
            "summary": self.summary,
            "flags": self.flags,
            "details": self.details,
            "metas": self.metas,
            # raw responses stored separately in files to keep report smaller
            "raw_response_count": len(self.raw_responses),
        }


VERDICT_LABELS = ("高度疑似", "较为接近", "无法确认", "存在明显异常")
