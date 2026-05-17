576"""
Programmatic intelligence layer — runs before the LLM.
Handles deduplication, importance scoring, hype detection, and escalation.
The LLM then reasons on top of this pre-processed, structured output.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Config ────────────────────────────────────────────────────────────────────

SOURCE_TIER: dict[str, float] = {
    "company_blog": 3.0,
    "media":        2.0,
    "newsletter":   2.0,
    "research":     2.5,
    "reddit":       1.0,
}

IMPORTANCE_HIGH: set[str] = {
    "gpt-5", "gpt5", "claude 4", "claude 5", "claude opus", "gemini ultra",
    "llama 4", "llama 5", "mistral large", "agi", "general intelligence",
    "raises", "funding round", "acquires", "acquisition", "merger",
    "billion", "regulation", "executive order", "banned", "ban",
    "open source", "open-source", "jailbreak", "vulnerability",
    "safety incident", "emergency", "breakthrough", "landmark",
}

IMPORTANCE_MEDIUM: set[str] = {
    "releases", "launches", "new model", "update", "version",
    "partnership", "benchmark", "outperforms", "beats", "surpasses",
    "paper", "study", "report", "fine-tun", "finetun",
}

HYPE_PHRASES: list[str] = [
    "revolutionary", "unprecedented", "game-changer", "game-changing",
    "changes everything", "everything will change", "nothing will be the same",
    "most powerful", "most capable", "most advanced ever",
    "blows away", "destroys", "obliterates", "crushes", "dominates",
    "the end of", "10x better", "100x better",
]

ESCALATION_TERMS: list[str] = [
    "gpt-5", "gpt5", "claude 4", "claude 5", "gemini ultra 2",
    "agi", "artificial general intelligence",
    "executive order", "regulation passes", "banned by",
    "$1b", "$10b", "1 billion", "10 billion",
    "major vulnerability", "security breach", "data leak", "emergency",
]

STOP_WORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "has", "have",
    "had", "will", "would", "could", "should", "this", "that", "it", "its",
    "be", "been", "being", "do", "does", "did", "not", "no", "new", "ai",
    "how", "what", "why", "when", "who", "which",
}


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class ArticleIntel:
    article_id: str
    importance: float = 0.0       # 0–10
    novelty: float = 1.0          # 0–1 (set by memory layer)
    is_duplicate: bool = False
    duplicate_of: str | None = None
    is_hype: bool = False
    escalate: bool = False
    escalation_reason: str = ""
    cluster_id: str | None = None
    tags: list[str] = field(default_factory=list)


# ── Token utilities ───────────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _age_hours(ts: str) -> float:
    if not ts:
        return 999.0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 0.0)
    except Exception:
        return 999.0


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_importance(article: dict) -> tuple[float, list[str]]:
    title   = (article.get("title")   or "").lower()
    summary = (article.get("summary") or "").lower()
    text    = f"{title} {summary}"
    tags: list[str] = []

    score = SOURCE_TIER.get(
        article.get("category") or article.get("source", ""), 1.0
    )

    for term in IMPORTANCE_HIGH:
        if term in text:
            score += 2.5
            tags.append(term)

    for term in IMPORTANCE_MEDIUM:
        if term in text:
            score += 1.0

    # Reddit engagement bonus
    if article.get("source") == "reddit":
        raw = article.get("score", 0) or 0
        score += min(raw / 800, 2.0)

    return min(round(score, 1), 10.0), tags[:5]


def _is_hype(article: dict) -> bool:
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    matches = sum(1 for phrase in HYPE_PHRASES if phrase in text)
    has_numbers = bool(re.search(r"\d+[%xkm b]|\$\d+|\d+\.\d+|\d{4}", text))
    return matches >= 2 and not has_numbers


def _check_escalation(article: dict, importance: float) -> tuple[bool, str]:
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    for term in ESCALATION_TERMS:
        if term in text:
            return True, f'"{term}"'
    if importance >= 8.5:
        return True, f"importance={importance}"
    return False, ""


# ── Main analysis pipeline ────────────────────────────────────────────────────

def analyze(articles: list[dict]) -> dict[str, ArticleIntel]:
    """
    Run full intelligence pipeline: score → dedup → cluster.
    Returns a map of article_id → ArticleIntel.
    """
    token_cache: dict[str, set[str]] = {
        a["id"]: _tokens(a.get("title", "")) for a in articles
    }
    intel: dict[str, ArticleIntel] = {}

    # Pass 1: score + hype + escalation
    for article in articles:
        aid = article["id"]
        importance, tags = _score_importance(article)
        escalate, reason = _check_escalation(article, importance)
        intel[aid] = ArticleIntel(
            article_id=aid,
            importance=importance,
            is_hype=_is_hype(article),
            escalate=escalate,
            escalation_reason=reason,
            tags=tags,
        )

    # Pass 2: deduplication (compare each against all earlier articles)
    for i, article in enumerate(articles):
        aid = article["id"]
        if intel[aid].is_duplicate:
            continue
        tok_a = token_cache[aid]
        for prev in articles[:i]:
            pid = prev["id"]
            if intel[pid].is_duplicate:
                continue
            if _jaccard(tok_a, token_cache[pid]) >= 0.55:
                intel[aid].is_duplicate = True
                intel[aid].duplicate_of = pid
                intel[aid].importance   *= 0.4
                break

    # Pass 3: clustering (group related non-duplicate articles)
    cluster_id = 0
    id_to_cluster: dict[str, str] = {}
    for i, article in enumerate(articles):
        aid = article["id"]
        if intel[aid].is_duplicate:
            continue
        tok_a = token_cache[aid]
        best_pid, best_sim = None, 0.0
        for prev in articles[:i]:
            pid = prev["id"]
            if intel[pid].is_duplicate:
                continue
            sim = _jaccard(tok_a, token_cache[pid])
            if sim >= 0.30 and sim > best_sim:
                best_sim = sim
                best_pid = pid
        if best_pid and best_pid in id_to_cluster:
            cid = id_to_cluster[best_pid]
        else:
            cid = f"c{cluster_id}"
            cluster_id += 1
        id_to_cluster[aid] = cid
        intel[aid].cluster_id = cid

    return intel


# ── LLM context formatter ─────────────────────────────────────────────────────

def format_brief(articles: list[dict], intel: dict[str, ArticleIntel]) -> str:
    """Format pre-processed intelligence into a compact brief for the LLM."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    total      = len(articles)
    dupes      = sum(1 for v in intel.values() if v.is_duplicate)
    escalated  = [a for a in articles if intel[a["id"]].escalate and not intel[a["id"]].is_duplicate]
    hype_items = [a for a in articles if intel[a["id"]].is_hype and not intel[a["id"]].is_duplicate]
    notable    = sorted(
        [a for a in articles if not intel[a["id"]].is_duplicate and not intel[a["id"]].escalate],
        key=lambda x: intel[x["id"]].importance,
        reverse=True,
    )

    lines = [
        f"=== HERMES INTELLIGENCE BRIEF — {now} ===",
        f"Processed: {total} articles | Duplicates filtered: {dupes} | "
        f"Escalated: {len(escalated)} | Hype flagged: {len(hype_items)}",
        "",
    ]

    if escalated:
        lines.append("🚨 BREAKING / ESCALATED:")
        for a in escalated[:6]:
            i = intel[a["id"]]
            lines.append(f"  [{i.importance:.1f}] {a.get('title')}")
            lines.append(f"       Source: {a.get('source_name', a.get('source'))}  URL: {a.get('url')}")
            if a.get("summary"):
                lines.append(f"       {a['summary'][:200]}")
        lines.append("")

    lines.append("📌 HIGH-IMPORTANCE (non-duplicate, ranked):")
    for a in notable[:20]:
        i = intel[a["id"]]
        if i.importance < 3:
            break
        hype_flag = " ⚠️HYPE" if i.is_hype else ""
        lines.append(f"  [{i.importance:.1f}]{hype_flag} {a.get('title')}")
        lines.append(f"       Source: {a.get('source_name', a.get('source'))}  URL: {a.get('url')}")
        if a.get("summary"):
            lines.append(f"       {a['summary'][:180]}")
    lines.append("")

    if hype_items:
        lines.append("⚠️  HYPE-FLAGGED (vague superlatives, no concrete data):")
        for a in hype_items[:5]:
            lines.append(f"  {a.get('title')} ({a.get('source_name', a.get('source'))})")
        lines.append("")

    return "\n".join(lines)
