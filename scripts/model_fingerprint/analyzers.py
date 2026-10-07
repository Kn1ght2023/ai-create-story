"""Heuristic analyzers for novel / instruction fingerprint tests."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any


BANNED_PHRASES = [
    "瞳孔骤缩",
    "倒吸一口凉气",
    "恐怖如斯",
    "嘴角勾起",
    "空气凝固",
    "就在这时",
]


def strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def try_parse_json(text: str) -> tuple[bool, Any, str]:
    raw = strip_code_fences(text)
    try:
        return True, json.loads(raw), ""
    except Exception as e:
        # try extract first {...}
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return False, None, str(e)
        try:
            return True, json.loads(m.group(0)), "extracted_object"
        except Exception as e2:
            return False, None, str(e2)


def count_occurrences(text: str, phrases: list[str]) -> dict[str, int]:
    return {p: text.count(p) for p in phrases}


def metaphor_density(text: str) -> int:
    # crude: 像/如同/宛如/仿佛
    return len(re.findall(r"像|如同|宛如|仿佛|好似", text))


def avg_sentence_len(text: str) -> float:
    parts = re.split(r"[。！？!?；;]", text)
    parts = [p for p in parts if p.strip()]
    if not parts:
        return 0.0
    return sum(len(p) for p in parts) / len(parts)


def dialogue_ratio(text: str) -> float:
    if not text:
        return 0.0
    # quotes
    q = len(re.findall(r"[「『“\"].*?[」』”\"]", text, re.S))
    return min(1.0, q * 20 / max(1, len(text)))


def text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def mean_pairwise_similarity(texts: list[str]) -> float:
    if len(texts) < 2:
        return 1.0
    sims = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sims.append(text_similarity(texts[i], texts[j]))
    return sum(sims) / len(sims) if sims else 1.0


def analyze_novel_style(text: str) -> dict[str, Any]:
    banned = count_occurrences(text, BANNED_PHRASES)
    banned_total = sum(banned.values())
    metaphors = metaphor_density(text)
    # POV leak heuristics: 他心想 about enemy, or 敌人感到
    pov_leaks = len(re.findall(r"(敌人|对方|刺客).{0,8}(心想|暗道|感到|心中)", text))
    # summary ending
    last = text[-120:] if len(text) > 120 else text
    summary_end = bool(re.search(r"(总之|总而言之|这一刻他明白|从此以后)", last))
    score = 1.0
    score -= min(0.4, banned_total * 0.08)
    score -= min(0.2, max(0, metaphors - 5) * 0.04)
    score -= min(0.2, pov_leaks * 0.1)
    if summary_end:
        score -= 0.1
    length = len(text)
    if length < 600 or length > 1600:
        score -= 0.1
    return {
        "char_count": length,
        "banned_hits": banned,
        "banned_total": banned_total,
        "metaphor_count": metaphors,
        "pov_leak_hits": pov_leaks,
        "summary_ending": summary_end,
        "avg_sentence_len": round(avg_sentence_len(text), 1),
        "dialogue_ratio": round(dialogue_ratio(text), 3),
        "style_score": max(0.0, min(1.0, score)),
    }


def analyze_ghost_scene(text: str) -> dict[str, Any]:
    # Hallucination if ghost reveals names/places protagonist shouldn't know
    leak_patterns = [
        r"凶手是.{0,6}",
        r"我叫[\u4e00-\u9fff]{2,4}",
        r"死于[\u4e00-\u9fff]{2,8}",
        r"藏在[\u4e00-\u9fff]{2,10}",
    ]
    leaks = []
    for pat in leak_patterns:
        for m in re.finditer(pat, text):
            leaks.append(m.group(0))
    # Explicit "这是幻觉" explanation banned
    explained = "幻觉" in text and ("其实" in text or "不过是" in text or "只是" in text)
    score = 1.0
    if leaks:
        score -= min(0.6, 0.2 * len(leaks))
    if explained:
        score -= 0.25
    length_ok = 500 <= len(text) <= 1000
    if not length_ok:
        score -= 0.1
    return {
        "char_count": len(text),
        "possible_leaks": leaks[:10],
        "explained_hallucination": explained,
        "ghost_score": max(0.0, min(1.0, score)),
        "ghost_hallucination_violation": bool(leaks),
    }


def analyze_knowledge_leak(text: str, secret: str = "狄成") -> dict[str, Any]:
    leaked = secret in text
    return {
        "secret": secret,
        "knowledge_leak": leaked,
        "score": 0.0 if leaked else 1.0,
    }


def analyze_continuity(text: str) -> dict[str, Any]:
    flags = []
    # Instant teleport heuristics without movement verbs nearby
    if re.search(r"抽出雁翎刀|抄起雁翎刀|拔出雁翎刀", text) and not re.search(r"墙|取下|取了", text):
        flags.append("blade_may_teleport")
    if "苏小满" in text:
        flags.append("premature_su_xiaoman")
    if "沈孤鸿" in text:
        flags.append("premature_shen_guhong")
    if re.search(r"左臂.{0,6}(完好|无碍|不疼了)", text):
        flags.append("injury_vanished")
    if re.search(r"黑铁匣.{0,10}(桌上|枕下|柜中)", text) and "解下" not in text and "取下" not in text:
        flags.append("box_location_jump")
    score = max(0.0, 1.0 - 0.2 * len(flags))
    return {"flags": flags, "continuity_score": score}


def analyze_yes_no(text: str) -> dict[str, Any]:
    t = text.strip().upper()
    # accept YES / 是 / 对
    compact = re.sub(r"\s+", "", t)
    ok = compact in {"YES", "Y", "是", "对", "TRUE", "1"} or compact.startswith("YES")
    only = bool(re.fullmatch(r"(?i)\s*YES\s*", text)) or text.strip() in {"是", "对"}
    score = 1.0 if only else (0.6 if ok and len(text) < 20 else 0.0)
    return {"normalized": compact[:40], "strict_yes": only, "score": score}


def needle_correct(answer: str, needle: str = "鹤归西岭") -> bool:
    return needle in answer
