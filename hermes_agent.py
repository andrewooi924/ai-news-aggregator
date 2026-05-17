"""
Hermes — Agentic AI News Intelligence Agent

Replaces the single-shot LLM call with a proper tool-calling loop.
Hermes3 decides what to fetch, which sources to query, whether to
deep-read a URL for missing facts, and when it has enough to answer.

The run_hermes_agent(query) interface is unchanged so app.py works as-is.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from typing import Any

import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

from sources.reddit import fetch_reddit_ai, DEFAULT_SUBREDDITS
from sources.rss_fetcher import fetch_rss_ai, RSS_FEEDS, FEED_CATEGORIES
from agents.intelligence import analyze, format_brief, ArticleIntel
from agents.memory import HermesMemory

load_dotenv()

_raw_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OLLAMA_BASE_URL = _raw_url if _raw_url.endswith("/v1") else _raw_url + "/v1"
MODEL = os.environ.get("OLLAMA_MODEL", "hermes3")

# Safety ceiling on tool-call rounds per query
MAX_LOOP_ITERATIONS = 8

_memory = HermesMemory()

# ── Shared article store (reset each agent run) ────────────────────────────────
# article_id → article dict; accumulates across all tool calls in one run
_article_store: dict[str, dict] = {}


# ── Tool implementations ───────────────────────────────────────────────────────

async def _tool_fetch_reddit(limit_per_sub: int = 10) -> str:
    articles = await fetch_reddit_ai(limit_per_sub=limit_per_sub)
    for a in articles:
        _article_store[a["id"]] = a
    intel = analyze(articles)
    for a in articles:
        url = a.get("url", "")
        if url and a["id"] in intel:
            intel[a["id"]].novelty = _memory.novelty(url)
    brief = format_brief(articles, intel)
    return f"Fetched {len(articles)} Reddit posts.\n\n{brief}"


async def _tool_fetch_rss(
    category: str | None = None,
    feeds: list[str] | None = None,
    limit_per_feed: int = 6,
) -> str:
    valid_categories = set(FEED_CATEGORIES.values())
    if category and category not in valid_categories:
        return f"Unknown category '{category}'. Valid: {sorted(valid_categories)}"
    if feeds:
        invalid = [f for f in feeds if f not in RSS_FEEDS]
        if invalid:
            return f"Unknown feed keys: {invalid}. Call list_sources to see valid keys."

    articles = await fetch_rss_ai(feeds=feeds, category=category, limit_per_feed=limit_per_feed)
    for a in articles:
        _article_store[a["id"]] = a
    intel = analyze(articles)
    for a in articles:
        url = a.get("url", "")
        if url and a["id"] in intel:
            intel[a["id"]].novelty = _memory.novelty(url)
    brief = format_brief(articles, intel)
    if category:
        source_desc = f"category={category}"
    elif feeds:
        source_desc = f"feeds={feeds}"
    else:
        source_desc = "all RSS"
    return f"Fetched {len(articles)} articles from {source_desc}.\n\n{brief}"


async def _tool_fetch_article(url: str) -> str:
    """Fetch the full text of an article to verify claims or get missing facts."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
            r = await client.get(url, headers={"User-Agent": "AI-News-Aggregator/1.0"})
            r.raise_for_status()
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:2500] if text else "Could not extract text from page."
    except Exception as e:
        return f"Failed to fetch {url}: {e}"


def _tool_search_articles(query: str) -> str:
    """Search already-fetched articles by keyword."""
    if not _article_store:
        return "No articles fetched yet. Use fetch_reddit or fetch_rss first."
    q = query.lower()
    matches = [
        a for a in _article_store.values()
        if q in (a.get("title") or "").lower()
        or q in (a.get("summary") or "").lower()
    ]
    if not matches:
        return f"No articles matched '{query}' in the {len(_article_store)} fetched so far."
    intel = analyze(matches)
    brief = format_brief(matches, intel)
    return f"Found {len(matches)} articles matching '{query}'.\n\n{brief}"


def _tool_list_sources() -> str:
    """List all available RSS feed keys grouped by category."""
    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for key, cat in FEED_CATEGORIES.items():
        by_cat[cat].append(key)
    lines = ["Available sources:\n\nSpecial: reddit\n"]
    for cat in sorted(by_cat):
        lines.append(f"[{cat}]")
        for key in sorted(by_cat[cat]):
            name, _ = RSS_FEEDS[key]
            lines.append(f"  {key:<35} {name}")
        lines.append("")
    return "\n".join(lines)


def _tool_analyze_fetched(top_n: int = 20) -> str:
    """
    Run the full intelligence pipeline over all articles fetched so far:
    deduplication, importance scoring, hype detection, clustering.
    """
    if not _article_store:
        return "No articles fetched yet."
    articles = list(_article_store.values())
    intel = analyze(articles)
    for a in articles:
        url = a.get("url", "")
        if url and a["id"] in intel:
            intel[a["id"]].novelty = _memory.novelty(url)
    brief = format_brief(articles, intel)
    return f"Intelligence analysis over {len(articles)} fetched articles:\n\n{brief}"


# ── Tool dispatch ──────────────────────────────────────────────────────────────

async def _dispatch_tool(name: str, args: dict) -> str:
    match name:
        case "fetch_reddit":
            return await _tool_fetch_reddit(**args)
        case "fetch_rss":
            return await _tool_fetch_rss(**args)
        case "fetch_article":
            return await _tool_fetch_article(**args)
        case "search_articles":
            return _tool_search_articles(**args)
        case "list_sources":
            return _tool_list_sources()
        case "analyze_fetched":
            return _tool_analyze_fetched(**args)
        case _:
            return f"Unknown tool: {name}"


# ── Tool schemas ───────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_reddit",
            "description": (
                "Fetch hot AI posts from Reddit (r/MachineLearning, r/LocalLLaMA, "
                "r/OpenAI, r/singularity, etc). Best for community reactions, "
                "trending discussions, and grassroots release announcements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit_per_sub": {
                        "type": "integer",
                        "description": "Posts per subreddit. Default 10.",
                        "default": 10,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_rss",
            "description": (
                "Fetch articles from RSS feeds. "
                "Use `category` for a broad pull: "
                "  'company_blog' — official announcements from OpenAI, Anthropic, Google, Meta, etc; "
                "  'research'     — Hugging Face papers, Papers With Code; "
                "  'media'        — TechCrunch, The Verge, Wired, MIT Tech Review; "
                "  'newsletter'   — The Rundown AI, Ben's Bites, TLDR AI, Latent Space, etc. "
                "Use `feeds` for specific sources by key (call list_sources to see keys). "
                "Omit both to fetch everything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["newsletter", "media", "company_blog", "research"],
                        "description": "Fetch all feeds in this category.",
                    },
                    "feeds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific feed keys, e.g. ['openai_blog', 'anthropic_blog'].",
                    },
                    "limit_per_feed": {
                        "type": "integer",
                        "description": "Articles per feed. Default 6.",
                        "default": 6,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_article",
            "description": (
                "Fetch the full text of a specific article URL. "
                "Use this when a summary is thin and you need concrete facts: "
                "version numbers, benchmark scores, funding amounts, specific claims."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the article to read.",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_articles",
            "description": (
                "Search already-fetched articles by keyword. "
                "Use after fetching to filter for a specific company, model, or topic "
                "without making another network call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword or phrase to search for.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sources",
            "description": (
                "List all available RSS feed keys grouped by category. "
                "Use this before calling fetch_rss with specific feed names."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_fetched",
            "description": (
                "Run the full intelligence pipeline over all articles fetched so far: "
                "deduplication, importance scoring (0–10), hype detection, and clustering. "
                "Use this after fetching multiple sources to get a unified ranked brief."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top articles to highlight. Default 20.",
                        "default": 20,
                    }
                },
                "required": [],
            },
        },
    },
]


# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are Hermes, an agentic AI news intelligence agent with tools to fetch, search, and analyze AI news.

## How to work

Think before fetching. Match your tool choice to what the query actually needs:
- Official announcements → fetch_rss with category="company_blog"
- New research / papers → fetch_rss with category="research"
- Industry analysis, journalism → fetch_rss with category="media"
- Community reaction, trending topics → fetch_reddit
- Curated takes and summaries → fetch_rss with category="newsletter"
- Specific company or topic → fetch then search_articles to filter
- Summary is thin but story looks important → fetch_article to get full text
- After gathering from multiple sources → analyze_fetched for a unified ranked view

Stop fetching when you have enough to answer confidently. Do not fetch everything by default.

## Response rules — no exceptions

1. Name every specific company, product, model, or person. Never "an AI company" or "a new model".
2. One concrete fact per story: version number, benchmark score, funding amount, release date, capability.
3. 2–4 sentences per story: what happened → key detail → why it matters.
4. Cite URLs as markdown links directly after each item.
5. Lead with 🚨 BREAKING items, then HIGH-IMPORTANCE, then themed groupings.
6. Flag ⚠️ HYPE items with a brief note explaining why they lack concrete data.
7. No filler: never say "this is significant", "the AI landscape continues to evolve", or similar.
8. For general digest requests, group by theme: ## Model Releases · ## Research · ## Industry & Funding · ## Tools & Products."""


# ── Agent loop ─────────────────────────────────────────────────────────────────

async def run_hermes_agent(query: str) -> str:
    """
    Agentic entry point. Drives a tool-calling loop until Hermes has
    gathered enough information to answer, then returns the final response.

    Interface is identical to the old single-shot version so app.py is unchanged.
    """
    global _article_store
    _article_store = {}  # fresh store per query

    client = AsyncOpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    print(f"[Hermes] Agentic loop starting — query: {query!r}", flush=True)

    final_content = ""

    for iteration in range(MAX_LOOP_ITERATIONS):
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        tool_calls = msg.tool_calls or []

        # Build the assistant turn for history
        assistant_turn: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_turn)

        # No tool calls → agent decided it's done
        if finish_reason == "stop" or not tool_calls:
            final_content = msg.content or ""
            print(
                f"[Hermes] Done after {iteration + 1} iteration(s) · "
                f"{len(_article_store)} articles in store.",
                flush=True,
            )
            break

        # Execute tool calls and collect results
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            print(f"[Hermes] → {fn_name}({fn_args})", flush=True)
            result = await _dispatch_tool(fn_name, fn_args)

            # Truncate large results to protect context window
            if len(result) > 6000:
                result = result[:6000] + "\n… [truncated — call search_articles to drill in]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    else:
        # Hit the iteration ceiling — force a final synthesis
        print(f"[Hermes] Hit {MAX_LOOP_ITERATIONS}-iteration limit; forcing synthesis.", flush=True)
        messages.append({
            "role": "user",
            "content": (
                "You've reached the research limit. "
                "Synthesize everything gathered and give your final answer now."
            ),
        })
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=4096,
        )
        final_content = response.choices[0].message.content or ""

    # Persist seen articles and session to memory
    if _article_store:
        articles = list(_article_store.values())
        intel = analyze(articles)
        n_dupes = sum(1 for v in intel.values() if v.is_duplicate)
        n_escalate = sum(1 for v in intel.values() if v.escalate and not v.is_duplicate)
        _memory.mark_seen(articles, intel)
        _memory.add_session(
            brief_summary=final_content[:400],
            stats={
                "articles_fetched": len(articles),
                "duplicates_filtered": n_dupes,
                "escalated": n_escalate,
                "query": query[:200],
            },
        )

    return final_content


# ── CLI ────────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes — Agentic AI News Intelligence Agent (CLI)"
    )
    parser.add_argument(
        "--list-sources",
        help="Print all available source keys and exit.",
        action="store_true",
    )
    args = parser.parse_args()

    if args.list_sources:
        print(_tool_list_sources())
        sys.exit(0)

    print("=" * 60)
    print("  HERMES — Agentic AI News Intelligence Agent")
    print(f"  Model     : {MODEL}")
    print(f"  Memory    : {_memory.total_seen} URLs tracked")
    print(f"  Mode      : Agentic tool-calling loop (max {MAX_LOOP_ITERATIONS} rounds)")
    print("=" * 60)

    while True:
        try:
            query = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print("\nHermes: ", end="", flush=True)
        try:
            answer = await run_hermes_agent(query)
            print(answer)
        except Exception as e:
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                print(f"ERROR: Cannot reach Ollama at {OLLAMA_BASE_URL}")
                sys.exit(1)
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())