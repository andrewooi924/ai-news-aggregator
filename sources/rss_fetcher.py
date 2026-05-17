import asyncio
import hashlib
from datetime import datetime
from typing import Any
import httpx
import feedparser

HEADERS = {"User-Agent": "AI-News-Aggregator/1.0 (MCP Server)"}

# ── Newsletters ───────────────────────────────────────────────────────────────
NEWSLETTER_FEEDS: dict[str, tuple[str, str]] = {
    "the_rundown_ai":   ("The Rundown AI",          "https://www.therundown.ai/feed"),
    "superhuman_ai":    ("Superhuman AI",            "https://www.superhumanai.com/feed"),
    "bens_bites":       ("Ben's Bites",              "https://bensbites.beehiiv.com/feed"),
    "the_neuron":       ("The Neuron",               "https://www.theneurondaily.com/feed"),
    "tldr_ai":          ("TLDR AI",                  "https://tldr.tech/ai/rss"),
    "import_ai":        ("Import AI",                "https://importai.substack.com/feed"),
    "the_batch":        ("The Batch (DeepLearning.AI)", "https://www.deeplearning.ai/the-batch/feed/"),
    "alpha_signal":     ("AlphaSignal",              "https://alphasignal.ai/feed"),
    "turing_post":      ("Turing Post",              "https://www.turingpost.com/feed"),
    "latent_space":     ("Latent Space",             "https://www.latent.space/feed"),
    "smol_ai_news":     ("Smol AI News",             "https://news.smol.ai/rss"),
    "chain_of_thought": ("Chain of Thought",         "https://www.chainofthought.xyz/feed"),
}

# ── Media / Journalism ────────────────────────────────────────────────────────
MEDIA_FEEDS: dict[str, tuple[str, str]] = {
    "techcrunch_ai":    ("TechCrunch AI",            "https://techcrunch.com/tag/artificial-intelligence/feed/"),
    "the_verge_ai":     ("The Verge AI",             "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    "wired_ai":         ("Wired AI",                 "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss"),
    "mit_tech_review":  ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    "ars_technica":     ("Ars Technica",             "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    "venturebeat_ai":   ("VentureBeat AI",           "https://venturebeat.com/category/ai/feed/"),
    "ieee_spectrum_ai": ("IEEE Spectrum AI",         "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss"),
    "semafor_tech":     ("Semafor Technology",       "https://www.semafor.com/rss/technology.xml"),
    "axios_ai":         ("Axios",                    "https://api.axios.com/feed/"),
}

# ── Company Blogs ─────────────────────────────────────────────────────────────
COMPANY_BLOG_FEEDS: dict[str, tuple[str, str]] = {
    "openai_blog":      ("OpenAI Blog",              "https://openai.com/blog/rss.xml"),
    "anthropic_blog":   ("Anthropic Blog",           "https://www.anthropic.com/rss.xml"),
    "google_deepmind":  ("Google DeepMind Blog",     "https://deepmind.google/blog/feed/basic/"),
    "google_ai_blog":   ("Google AI Blog",           "https://blog.google/technology/ai/rss/"),
    "meta_ai":          ("Meta AI Blog",             "https://ai.meta.com/blog/rss/"),
    "nvidia_ai":        ("NVIDIA AI Blog",           "https://blogs.nvidia.com/blog/category/deep-learning/feed/"),
    "huggingface_blog": ("Hugging Face Blog",        "https://huggingface.co/blog/feed.xml"),
    "mistral_ai":       ("Mistral AI News",          "https://mistral.ai/news/feed.xml"),
}

# ── Research ──────────────────────────────────────────────────────────────────
RESEARCH_FEEDS: dict[str, tuple[str, str]] = {
    "huggingface_papers": ("Hugging Face Papers",    "https://huggingface.co/papers/rss"),
    "paperswithcode":   ("Papers With Code",         "https://paperswithcode.com/rss"),
}

# ── Podcasts ──────────────────────────────────────────────────────────────────
PODCAST_FEEDS: dict[str, tuple[str, str]] = {
    "lex_fridman":          ("Lex Fridman Podcast",          "https://lexfridman.com/feed/podcast/"),
    "dwarkesh":             ("Dwarkesh Podcast",             "https://www.dwarkeshpatel.com/feed"),
    "hard_fork":            ("Hard Fork (NYT)",              "https://feeds.simplecast.com/hI39a05U"),
    "twiml_ai":             ("TWIML AI Podcast",             "https://twimlai.com/feed/"),
    "mlst":                 ("Machine Learning Street Talk", "https://feeds.buzzsprout.com/1558559.rss"),
    "cognitive_revolution": ("The Cognitive Revolution",     "https://www.cognitiverevolution.ai/feed"),
}

# ── YouTube (Atom RSS via channel ID) ─────────────────────────────────────────
def _yt(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

YOUTUBE_FEEDS: dict[str, tuple[str, str]] = {
    "two_minute_papers": ("Two Minute Papers", _yt("UCbfYPyITQ-7l4upoX8nvctg")),
    "yannic_kilcher":    ("Yannic Kilcher",     _yt("UCZHmQk67mSJgfCCTn7xBfew")),
    "ai_explained":      ("AI Explained",       _yt("UCNJ1Ymd5yFuUPtn21xtRbbw")),
    "fireship":          ("Fireship",           _yt("UCsBjURrPoezykLs9EqgamOA")),
    "networkchuck":      ("NetworkChuck",       _yt("UC9x0AN7kwqBxTaT7sHkdlbw")),
    "matt_wolfe":        ("Matt Wolfe",         _yt("UCNKZ5lp1lcNmOz02kZAFmSw")),
    "all_about_ai":      ("All About AI",       _yt("UCbHRjQFzFI2E2G2KJ3FrBtw")),
    "the_ai_grid":       ("The AI Grid",        _yt("UCwkjsRlXLaQ3VlC7UNgNlGg")),
    "lex_fridman_yt":    ("Lex Fridman",        _yt("UCSHZKyawb77ixDdsGog4iWA")),
}

# ── Community ─────────────────────────────────────────────────────────────────
COMMUNITY_FEEDS: dict[str, tuple[str, str]] = {
    "lobsters_ai":   ("Lobsters AI",              "https://lobste.rs/t/ai.rss"),
    "openai_forum":  ("OpenAI Developer Forum",   "https://community.openai.com/latest.rss"),
}

# ── Combined ──────────────────────────────────────────────────────────────────
RSS_FEEDS: dict[str, tuple[str, str]] = {
    **NEWSLETTER_FEEDS,
    **MEDIA_FEEDS,
    **COMPANY_BLOG_FEEDS,
    **RESEARCH_FEEDS,
}

FEED_CATEGORIES: dict[str, str] = {
    **{k: "newsletter"   for k in NEWSLETTER_FEEDS},
    **{k: "media"        for k in MEDIA_FEEDS},
    **{k: "company_blog" for k in COMPANY_BLOG_FEEDS},
    **{k: "research"     for k in RESEARCH_FEEDS},
}


def _extract_image(entry) -> str:
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url", "")
        if url:
            return url
    if hasattr(entry, "media_content") and entry.media_content:
        for mc in entry.media_content:
            url = mc.get("url", "")
            if url and mc.get("type", "").startswith("image"):
                return url
        url = entry.media_content[0].get("url", "")
        if url:
            return url
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("url", "")
    return ""


def _parse_feed(content: bytes, source_key: str, source_name: str) -> list[dict[str, Any]]:
    feed = feedparser.parse(content)
    results = []
    for entry in feed.entries:
        title = getattr(entry, "title", "")
        url = getattr(entry, "link", "")
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        summary = summary[:400] + ("..." if len(summary) > 400 else "") if summary else ""

        published = ""
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    published = datetime(*parsed[:6]).isoformat()
                    break
                except Exception:
                    pass

        uid = hashlib.md5(url.encode()).hexdigest()[:12]
        results.append({
            "id": uid,
            "title": title,
            "url": url,
            "summary": summary,
            "image_url": _extract_image(entry),
            "time": published,
            "source": source_key,
            "source_name": source_name,
            "category": FEED_CATEGORIES.get(source_key, "other"),
        })
    return results


async def fetch_feed(
    client: httpx.AsyncClient,
    source_key: str,
    source_name: str,
    url: str,
    limit: int,
    sem: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    async with sem:
        try:
            r = await client.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
            r.raise_for_status()
            content = r.content
            loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(None, _parse_feed, content, source_key, source_name)
            return entries[:limit]
        except Exception:
            return []


async def fetch_rss_ai(
    feeds: list[str] | None = None,
    category: str | None = None,
    limit_per_feed: int = 10,
) -> list[dict[str, Any]]:
    if feeds is not None:
        selected = {k: v for k, v in RSS_FEEDS.items() if k in feeds}
    elif category is not None:
        selected = {k: v for k, v in RSS_FEEDS.items() if FEED_CATEGORIES.get(k) == category}
    else:
        selected = RSS_FEEDS

    sem = asyncio.Semaphore(10)  # created per-call to avoid event-loop binding issues
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_feed(client, key, name, url, limit_per_feed, sem)
            for key, (name, url) in selected.items()
        ]
        results = await asyncio.gather(*tasks)

    all_entries = [entry for feed_entries in results for entry in feed_entries]
    all_entries.sort(key=lambda x: x["time"], reverse=True)
    return all_entries


def list_rss_sources() -> dict[str, dict]:
    return {
        key: {"name": name, "category": FEED_CATEGORIES.get(key, "other")}
        for key, (name, _) in RSS_FEEDS.items()
    }
