"""Run fingerprint suite and persist per-test artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .client import OpenAICompatClient
from .tests import select_tests
from .types import RunConfig, TestResult


def run_fingerprint(client: OpenAICompatClient, cfg: RunConfig) -> dict[str, Any]:
    out = Path(cfg.out_dir)
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    def progress(msg: str) -> None:
        print(msg, flush=True)

    started = time.time()
    results: list[TestResult] = []
    ok = True

    for fn in select_tests(cfg):
        try:
            tr = fn(client, cfg, progress)
        except Exception as e:
            tr = TestResult(
                test_id=getattr(fn, "__name__", "unknown"),
                name=getattr(fn, "__name__", "unknown"),
                category="error",
                score=0,
                weight=5,
                status="error",
                summary=f"测试异常: {type(e).__name__}",
                flags=["test_exception"],
                details={"error_type": type(e).__name__},
            )
            ok = False
        results.append(tr)
        # persist raw (may contain model output; never api key)
        raw_path = raw_dir / f"{tr.test_id}.json"
        safe_raw = {
            "test_id": tr.test_id,
            "metas": tr.metas,
            "details": tr.details,
            "raw_responses": _sanitize(tr.raw_responses),
        }
        raw_path.write_text(json.dumps(safe_raw, ensure_ascii=False, indent=2), encoding="utf-8")
        # save novel full text for blind review
        if tr.test_id in {"T05_novel", "T06_ghost", "T07_knowledge", "T08_continuity"}:
            for item in tr.raw_responses:
                if isinstance(item, dict) and item.get("content"):
                    (out / f"{tr.test_id}.txt").write_text(item["content"], encoding="utf-8")
                    break
        print(f"  → {tr.test_id} [{tr.status}] score={tr.score:.2f} {tr.summary}", flush=True)

    elapsed = time.time() - started
    return {
        "ok": ok and all(r.status != "error" for r in results),
        "started_unix": started,
        "elapsed_seconds": round(elapsed, 1),
        "tests": results,
        "meta_models": _collect_response_models(results),
    }


def _sanitize(obj: Any) -> Any:
    """Drop anything that looks like an API key string pattern from nested structures."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if k.lower() not in {"api_key", "authorization"}}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, str) and obj.startswith("sk-") and len(obj) > 20:
        return "[redacted]"
    return obj


def _collect_response_models(results: list[TestResult]) -> list[str]:
    models = set()
    for r in results:
        for m in r.metas:
            if m.get("response_model"):
                models.add(m["response_model"])
    return sorted(models)
