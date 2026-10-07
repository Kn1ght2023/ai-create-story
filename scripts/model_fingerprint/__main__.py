#!/usr/bin/env python3
"""AI Model Fingerprint Tester — black-box proxy/alias detection (MVP).

Usage:
  python3 -m scripts.model_fingerprint --base-url https://api.example.com/v1 \\
    --api-key sk-xxx --model claude-sonnet-5 --mode standard

Never logs the API key. Reports use probabilistic language only
(高度疑似 / 较为接近 / 无法确认 / 存在明显异常).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

from .client import OpenAICompatClient, mask_key
from .report import build_report, export_json, export_markdown
from .runner import run_fingerprint
from .types import RunConfig


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="第三方大模型指纹检测（黑盒概率判断，非身份认证）",
    )
    p.add_argument("--provider-name", default="unnamed", help="显示用 Provider 名称")
    p.add_argument("--base-url", required=True, help="OpenAI Compatible Base URL")
    p.add_argument("--api-key", default=os.environ.get("FINGERPRINT_API_KEY", ""), help="API Key（也可用环境变量 FINGERPRINT_API_KEY）")
    p.add_argument("--model", required=True, help="声明的 Model ID")
    p.add_argument("--timeout", type=int, default=180, help="单次请求超时秒数")
    p.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--enable-long-context", action="store_true", default=True)
    p.add_argument("--no-long-context", action="store_true", help="跳过 100K Needle")
    p.add_argument("--enable-stream", action="store_true", default=True)
    p.add_argument("--no-stream", action="store_true", help="跳过流式指纹")
    p.add_argument("--repeats", type=int, default=3, help="同 Prompt 重复次数")
    p.add_argument("--out-dir", default="", help="报告输出目录（默认 ./fingerprint_runs/<run_id>）")
    p.add_argument("--claimed-family", default="claude", choices=["claude", "openai", "gemini", "deepseek", "unknown"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.api_key:
        print("错误: 请通过 --api-key 或环境变量 FINGERPRINT_API_KEY 提供密钥", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    out_dir = Path(args.out_dir) if args.out_dir else Path("fingerprint_runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = RunConfig(
        run_id=run_id,
        provider_name=args.provider_name,
        base_url=args.base_url.rstrip("/"),
        api_key=args.api_key,
        model=args.model,
        claimed_family=args.claimed_family,
        timeout_seconds=args.timeout,
        mode=args.mode,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        enable_long_context=args.enable_long_context and not args.no_long_context,
        enable_stream=args.enable_stream and not args.no_stream,
        repeats=max(1, args.repeats),
        out_dir=str(out_dir),
    )

    print(f"run_id={cfg.run_id}")
    print(f"provider={cfg.provider_name}")
    print(f"base_url={cfg.base_url}")
    print(f"model={cfg.model}")
    print(f"api_key={mask_key(cfg.api_key)}")
    print(f"mode={cfg.mode} repeats={cfg.repeats}")
    print(f"out_dir={out_dir}")
    print("---")
    print("注意: 本工具仅做黑盒行为相似度判断，不能证明真实上游模型身份。")
    print("---")

    client = OpenAICompatClient(cfg.base_url, cfg.api_key, timeout=cfg.timeout_seconds)
    result = run_fingerprint(client, cfg)
    report = build_report(cfg, result)

    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    export_json(report, json_path)
    export_markdown(report, md_path)

    print()
    print(report["summary_text"])
    print()
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
