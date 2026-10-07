"""OpenAI-compatible HTTP client. Never logs API keys."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from .types import CallMeta


def mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:3] + "****" + key[-4:]


def _join_url(base: str, path: str) -> str:
    base = base.rstrip("/") + "/"
    if path.startswith("/"):
        path = path[1:]
    # If base already ends with /v1 and path is models → /v1/models
    return urljoin(base, path)


def resolve_chat_url(base_url: str) -> str:
    """Mirror project logic loosely: ensure .../chat/completions."""
    u = base_url.rstrip("/")
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1") or "/v1/" in urlparse(u).path or u.rstrip("/").endswith("/v1"):
        return u + "/chat/completions"
    # bare host or custom path: append /v1/chat/completions if no version segment
    path = urlparse(u).path or ""
    if "/chat/completions" in path:
        return u
    if path in ("", "/"):
        return u + "/v1/chat/completions"
    return u + "/chat/completions"


def resolve_models_url(base_url: str) -> str:
    u = base_url.rstrip("/")
    if u.endswith("/models"):
        return u
    if u.endswith("/chat/completions"):
        return u[: -len("/chat/completions")] + "/models"
    if u.endswith("/v1") or u.rstrip("/").endswith("/v1"):
        return u + "/models"
    path = urlparse(u).path or ""
    if path in ("", "/"):
        return u + "/v1/models"
    return u + "/models"


def estimate_tokens(text: str) -> int:
    """Rough local estimate: CJK ~1.5 token/char, latin ~0.3 token/char."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk * 1.5 + other * 0.3))


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 180, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.chat_url = resolve_chat_url(self.base_url)
        self.models_url = resolve_models_url(self.base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request_json(self, method: str, url: str, body: dict | None = None) -> tuple[int, dict[str, str], Any, float]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                elapsed = (time.perf_counter() - t0) * 1000
                headers = {k: v for k, v in resp.headers.items()}
                try:
                    payload = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    payload = {"_raw_text": raw.decode("utf-8", errors="replace")[:8000]}
                return resp.status, headers, payload, elapsed
        except urllib.error.HTTPError as e:
            elapsed = (time.perf_counter() - t0) * 1000
            raw = e.read() if e.fp else b""
            headers = {k: v for k, v in (e.headers.items() if e.headers else [])}
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                payload = {"_raw_text": raw.decode("utf-8", errors="replace")[:8000]}
            return e.code, headers, payload, elapsed
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return 0, {}, {"error": type(e).__name__}, elapsed

    def list_models(self) -> tuple[CallMeta, Any]:
        meta = CallMeta()
        status, headers, payload, ms = self._request_json("GET", self.models_url)
        meta.http_status = status
        meta.latency_ms = ms
        meta.headers = headers
        if status == 0 or status >= 400:
            meta.error = str(payload.get("error") or payload)[:500]
        return meta, payload

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> tuple[str, CallMeta, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            body["stream_options"] = {"include_usage": True}
            return self._chat_stream(body)

        last_err = ""
        for attempt in range(self.max_retries + 1):
            status, headers, payload, ms = self._request_json("POST", self.chat_url, body)
            meta = CallMeta(http_status=status, latency_ms=ms, headers=headers)
            if status and status < 400 and isinstance(payload, dict):
                self._fill_meta_from_response(meta, payload)
                content = self._extract_content(payload)
                return content, meta, payload
            last_err = str(payload.get("error") or payload)[:500] if isinstance(payload, dict) else str(payload)[:500]
            meta.error = last_err
            if attempt < self.max_retries and status in (0, 429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            return "", meta, payload
        return "", CallMeta(error=last_err), {"error": last_err}

    def _chat_stream(self, body: dict[str, Any]) -> tuple[str, CallMeta, Any]:
        meta = CallMeta(streamed=True)
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.chat_url, data=data, headers=self._headers(), method="POST")
        t0 = time.perf_counter()
        chunks: list[str] = []
        raw_events: list[Any] = []
        usage = None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                meta.http_status = resp.status
                meta.headers = {k: v for k, v in resp.headers.items()}
                first = True
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    raw_events.append(obj)
                    meta.chunk_count += 1
                    if first:
                        meta.ttft_ms = (time.perf_counter() - t0) * 1000
                        first = False
                    if isinstance(obj.get("usage"), dict):
                        usage = obj["usage"]
                    choices = obj.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        if delta.get("content"):
                            chunks.append(delta["content"])
                        if choices[0].get("finish_reason"):
                            meta.finish_reason = choices[0]["finish_reason"]
                        if obj.get("model"):
                            meta.response_model = obj["model"]
                        if obj.get("id"):
                            meta.response_id = obj["id"]
                meta.latency_ms = (time.perf_counter() - t0) * 1000
                if usage:
                    meta.prompt_tokens = usage.get("prompt_tokens")
                    meta.completion_tokens = usage.get("completion_tokens")
                    meta.total_tokens = usage.get("total_tokens")
                text = "".join(chunks)
                return text, meta, {"stream_events_sample": raw_events[:5], "stream_event_count": len(raw_events), "content": text, "usage": usage}
        except urllib.error.HTTPError as e:
            meta.latency_ms = (time.perf_counter() - t0) * 1000
            meta.http_status = e.code
            raw = e.read() if e.fp else b""
            meta.error = raw.decode("utf-8", errors="replace")[:500]
            return "", meta, {"error": meta.error}
        except Exception as e:
            meta.latency_ms = (time.perf_counter() - t0) * 1000
            meta.error = type(e).__name__
            return "", meta, {"error": meta.error}

    @staticmethod
    def _extract_content(payload: dict) -> str:
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except Exception:
            return ""

    @staticmethod
    def _fill_meta_from_response(meta: CallMeta, payload: dict) -> None:
        meta.response_id = str(payload.get("id") or "")
        meta.response_model = str(payload.get("model") or "")
        meta.system_fingerprint = str(payload.get("system_fingerprint") or "")
        usage = payload.get("usage") or {}
        if isinstance(usage, dict):
            meta.prompt_tokens = usage.get("prompt_tokens")
            meta.completion_tokens = usage.get("completion_tokens")
            meta.total_tokens = usage.get("total_tokens")
        try:
            meta.finish_reason = str(payload["choices"][0].get("finish_reason") or "")
        except Exception:
            pass
