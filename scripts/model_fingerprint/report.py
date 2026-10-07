"""Scoring and report export. Probabilistic labels only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .client import mask_key
from .types import RunConfig, TestResult, VERDICT_LABELS


FAMILY_KEYS = ("claude", "openai", "gemini", "deepseek")


def _weighted_score(tests: list[TestResult]) -> float:
    num = den = 0.0
    for t in tests:
        if t.status == "skip":
            continue
        num += t.score * t.weight
        den += t.weight
    return (num / den) if den else 0.0


def _category_scores(tests: list[TestResult]) -> dict[str, float]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for t in tests:
        if t.status == "skip":
            continue
        buckets.setdefault(t.category, []).append((t.score, t.weight))
    out = {}
    for cat, pairs in buckets.items():
        n = sum(s * w for s, w in pairs)
        d = sum(w for _, w in pairs)
        out[cat] = round(n / d, 3) if d else 0.0
    return out


def _risks(tests: list[TestResult]) -> dict[str, str]:
    flags = []
    for t in tests:
        flags.extend(t.flags)

    def level(score: int) -> str:
        if score >= 40:
            return "高"
        if score >= 20:
            return "中"
        return "低"

    alias = 0
    routing = 0
    billing = 0
    context = 0
    capability = 0

    if "dynamic_model_routing_risk" in flags or "output_instability" in flags:
        routing += 20
    if "token_billing_anomaly" in flags:
        billing += 30
    if "token_usage_suspicious" in flags or "token_usage_volatility" in flags:
        billing += 15
    if "context_claim_risk" in flags:
        context += 30
    if "knowledge_leak" in flags or "ghost_hallucination_violation" in flags:
        capability += 20
    # low JSON / instruction vs claimed strong model → capability mismatch
    for t in tests:
        if t.test_id == "T03_json" and t.score < 0.5:
            capability += 15
            alias += 10
        if t.test_id == "T04_conflict" and t.score < 0.4:
            capability += 10
        if t.test_id == "T09_needle_100k" and t.score < 0.4:
            context += 20

    # metadata model field churn
    models = set()
    for t in tests:
        for m in t.metas:
            if m.get("response_model"):
                models.add(m["response_model"])
    if len(models) > 1:
        routing += 20
        alias += 15

    return {
        "model_alias_risk": level(alias),
        "dynamic_routing_risk": level(routing),
        "token_usage_risk": level(billing),
        "context_claim_risk": level(context),
        "capability_mismatch_risk": level(capability),
        "_scores": {
            "alias": alias,
            "routing": routing,
            "billing": billing,
            "context": context,
            "capability": capability,
        },
    }


def _similarity_sketch(cfg: RunConfig, tests: list[TestResult], overall: float) -> dict[str, float]:
    """Heuristic behavior similarity — NOT true probability."""
    cats = _category_scores(tests)
    literary = cats.get("literary", overall)
    instruction = cats.get("instruction", overall)
    context = cats.get("context", overall)
    stability = cats.get("stability", overall)

    # Baseline template profiles (hand-tuned priors for sketch only)
    profiles = {
        "claude": {"literary": 0.85, "instruction": 0.88, "context": 0.80, "stability": 0.75},
        "openai": {"literary": 0.72, "instruction": 0.90, "context": 0.78, "stability": 0.80},
        "gemini": {"literary": 0.70, "instruction": 0.82, "context": 0.85, "stability": 0.70},
        "deepseek": {"literary": 0.78, "instruction": 0.80, "context": 0.75, "stability": 0.72},
    }
    observed = {
        "literary": literary,
        "instruction": instruction,
        "context": context if "context" in cats else overall,
        "stability": stability if "stability" in cats else overall,
    }

    sims = {}
    for fam, prof in profiles.items():
        # inverse distance
        dist = sum(abs(observed[k] - prof[k]) for k in observed) / len(observed)
        sims[f"{fam}_similarity"] = round(max(0.0, min(1.0, 1.0 - dist)), 3)

    # Boost claimed family slightly toward overall if overall strong
    key = f"{cfg.claimed_family}_similarity"
    if key in sims and overall > 0.7:
        sims[key] = round(min(1.0, sims[key] * 0.7 + overall * 0.3), 3)

    # unknown = 1 - max family sim (capped)
    best = max(sims.values()) if sims else 0
    sims["unknown_similarity"] = round(max(0.0, 1.0 - best), 3)
    return sims


def _verdict(cfg: RunConfig, sims: dict[str, float], risks: dict[str, str], overall: float) -> tuple[str, str]:
    claimed = cfg.claimed_family
    claimed_sim = sims.get(f"{claimed}_similarity", 0)
    high_risk = any(risks.get(k) == "高" for k in risks if not k.startswith("_"))

    if high_risk or overall < 0.45:
        label = "存在明显异常"
        text = (
            f"声明模型：{cfg.model}\n"
            f"行为整体分偏低或出现高风险项（别名/路由/上下文/计费/能力）。\n"
            f"结论：{label}。不建议将该接口直接视为官方 {claimed} 系列。\n"
            f"由于请求可能经过第三方代理，无法验证真实上游。"
        )
        return label, text

    if claimed_sim >= 0.75 and overall >= 0.7:
        label = "较为接近"
        text = (
            f"声明模型：{cfg.model}\n"
            f"{claimed} 行为相似度（启发式）：{claimed_sim:.0%}\n"
            f"最终判断：{label} {claimed} 系列模型行为特征，暂未发现明显替换信号。\n"
            f"但由于请求经过第三方代理，无法验证真实上游；亦不能 100% 证明身份。"
        )
        return label, text

    if claimed_sim >= 0.6:
        label = "高度疑似"
        text = (
            f"声明模型：{cfg.model}\n"
            f"{claimed} 行为相似度（启发式）：{claimed_sim:.0%}\n"
            f"最终判断：{label}接近声明族，但仍有偏差；建议对照官方接口复测。\n"
            f"接口返回的 model 字符串由服务商控制，不能单独作为真实性证明。"
        )
        return label, text

    label = "无法确认"
    text = (
        f"声明模型：{cfg.model}\n"
        f"{claimed} 行为相似度（启发式）：{claimed_sim:.0%}\n"
        f"最终判断：{label}与声明族的一致性；输出能力可能来自其他家族或混合路由。\n"
        f"请结合原始响应与对照 Provider 再判。"
    )
    return label, text


def build_report(cfg: RunConfig, result: dict[str, Any]) -> dict[str, Any]:
    tests: list[TestResult] = result["tests"]
    overall = _weighted_score(tests)
    risks = _risks(tests)
    sims = _similarity_sketch(cfg, tests, overall)
    verdict, summary_text = _verdict(cfg, sims, risks, overall)

    latencies = []
    ttfts = []
    for t in tests:
        for m in t.metas:
            if m.get("latency_ms"):
                latencies.append(m["latency_ms"])
            if m.get("ttft_ms"):
                ttfts.append(m["ttft_ms"])

    report = {
        "disclaimer": (
            "本报告为黑盒行为指纹的启发式判断，使用「行为相似度」而非真实概率；"
            "不得解读为 100% 真/假证明。允许措辞：" + " / ".join(VERDICT_LABELS)
        ),
        "run_id": cfg.run_id,
        "provider_name": cfg.provider_name,
        "base_url": cfg.base_url,
        "api_key_masked": mask_key(cfg.api_key),
        "claimed_model": cfg.model,
        "claimed_family": cfg.claimed_family,
        "mode": cfg.mode,
        "elapsed_seconds": result.get("elapsed_seconds"),
        "response_model_fields_seen": result.get("meta_models"),
        "overall_score": round(overall * 100, 1),
        "category_scores": _category_scores(tests),
        "behavior_similarity": sims,
        "risk": {k: v for k, v in risks.items() if not k.startswith("_")},
        "verdict": verdict,
        "summary_text": summary_text,
        "latency": {
            "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "avg_ttft_ms": round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
        },
        "tests": [t.to_dict() for t in tests],
    }
    return report


def export_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def export_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        f"# 大模型指纹检测报告 `{report['run_id']}`",
        "",
        f"> {report['disclaimer']}",
        "",
        "## 概要",
        "",
        f"- Provider: **{report['provider_name']}**",
        f"- Base URL: `{report['base_url']}`",
        f"- API Key: `{report['api_key_masked']}`",
        f"- 声明模型: `{report['claimed_model']}`",
        f"- 接口返回 model 字段曾见: `{report.get('response_model_fields_seen')}`",
        f"- 模式: {report['mode']}",
        f"- 整体分: **{report['overall_score']}** / 100",
        f"- 判定: **{report['verdict']}**",
        "",
        "```",
        report["summary_text"],
        "```",
        "",
        "## 行为相似度（启发式，非真实概率）",
        "",
    ]
    for k, v in report["behavior_similarity"].items():
        lines.append(f"- {k}: **{v:.0%}**")
    lines += ["", "## 风险", ""]
    for k, v in report["risk"].items():
        lines.append(f"- {k}: **{v}**")
    lines += ["", "## 分项测试", "", "| ID | 名称 | 状态 | 分 | 摘要 |", "|---|---|---|---|---|"]
    for t in report["tests"]:
        lines.append(f"| {t['test_id']} | {t['name']} | {t['status']} | {t['score']:.2f} | {t['summary'].replace('|', '/')} |")
    lines += [
        "",
        "## 延迟",
        "",
        f"- 平均响应: {report['latency'].get('avg_ms')} ms",
        f"- 平均 TTFT: {report['latency'].get('avg_ttft_ms')} ms",
        "",
        "原始响应见同目录 `raw/` 与各小说测试 `.txt`（供 Blind Review）。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
