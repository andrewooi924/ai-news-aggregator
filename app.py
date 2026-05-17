import asyncio
import math
from datetime import datetime, timezone

import nest_asyncio
nest_asyncio.apply()

import streamlit as st

from sources.reddit import fetch_reddit_ai
from sources.rss_fetcher import (
    fetch_rss_ai,
    RSS_FEEDS,
    NEWSLETTER_FEEDS,
    MEDIA_FEEDS,
    COMPANY_BLOG_FEEDS,
    RESEARCH_FEEDS,
)
from agents.intelligence import analyze, format_brief, ArticleIntel
from hermes_agent import run_hermes_agent

st.set_page_config(
    page_title="Hermes AI News",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 360px; max-width: 360px; }
.card {
    padding: 12px 14px;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    margin-bottom: 10px;
    overflow: hidden;
    position: relative;
}
.card img {
    width: 100%;
    max-height: 180px;
    object-fit: cover;
    border-radius: 5px;
    margin-bottom: 8px;
    display: block;
}
.card-title { font-size: 0.93rem; font-weight: 600; line-height: 1.35; }
.card-title a { color: inherit !important; text-decoration: none; }
.card-title a:hover { text-decoration: underline; }
.card-meta  { font-size: 0.72rem; color: #888; margin: 3px 0 6px; }
.card-body  { font-size: 0.81rem; color: #bbb; line-height: 1.5; }
.badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    margin-right: 4px;
    vertical-align: middle;
}
.badge-red    { background: #4a1a1a; color: #ff6b6b; border: 1px solid #ff6b6b44; }
.badge-orange { background: #3a2010; color: #ff9f43; border: 1px solid #ff9f4344; }
.badge-yellow { background: #2e2810; color: #feca57; border: 1px solid #feca5744; }
.badge-gray   { background: #252525; color: #888;    border: 1px solid #44444444; }
.badge-hype   { background: #2a1f0a; color: #e0a500; border: 1px solid #e0a50044; }
.badge-dupe   { background: #1a1a2a; color: #7f8cff; border: 1px solid #7f8cff44; }
.alert-banner {
    background: #1a0a0a;
    border: 1px solid #cc2222;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
}
.alert-banner h4 { color: #ff4444; margin: 0 0 8px; font-size: 0.9rem; }
.alert-item { font-size: 0.82rem; color: #ddd; margin: 4px 0; }
.alert-item a { color: #ff8888 !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d")
    except Exception:
        return ts[:10]


def _hotness(a: dict) -> float:
    score = a.get("score") or 0
    ts = a.get("time", "")
    if not ts:
        return float(score)
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = max((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 0.1)
        return (score + 1) / math.pow(hours + 2, 1.5)
    except Exception:
        return float(score)


def _apply_sort(articles: list[dict]) -> list[dict]:
    mode = st.session_state.get("sort_mode", "Latest")
    if mode == "Hottest":
        return sorted(articles, key=_hotness, reverse=True)
    if mode == "Top Scored":
        return sorted(articles, key=lambda x: x.get("score") or 0, reverse=True)
    return sorted(articles, key=lambda x: x.get("time", ""), reverse=True)


def _importance_badge(importance: float) -> str:
    score = f"{importance:.1f}"
    if importance >= 8:
        return f'<span class="badge badge-red">🔴 {score}</span>'
    if importance >= 6:
        return f'<span class="badge badge-orange">🟠 {score}</span>'
    if importance >= 4:
        return f'<span class="badge badge-yellow">🟡 {score}</span>'
    return f'<span class="badge badge-gray">⚪ {score}</span>'


# ── Cached fetchers ───────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def load_reddit() -> list[dict]:
    return asyncio.run(fetch_reddit_ai(limit_per_sub=10))

@st.cache_data(ttl=1800, show_spinner=False)
def load_newsletters() -> list[dict]:
    return asyncio.run(fetch_rss_ai(category="newsletter", limit_per_feed=8))

@st.cache_data(ttl=1800, show_spinner=False)
def load_media() -> list[dict]:
    return asyncio.run(fetch_rss_ai(category="media", limit_per_feed=8))

@st.cache_data(ttl=1800, show_spinner=False)
def load_company_blogs() -> list[dict]:
    return asyncio.run(fetch_rss_ai(category="company_blog", limit_per_feed=8))

@st.cache_data(ttl=1800, show_spinner=False)
def load_research() -> list[dict]:
    return asyncio.run(fetch_rss_ai(category="research", limit_per_feed=8))


# ── Article card ──────────────────────────────────────────────────────────────

def render_article(a: dict, intel: dict[str, ArticleIntel] | None = None) -> None:
    title     = (a.get("title") or "Untitled").strip().replace('"', "&quot;")
    url       = a.get("url") or "#"
    source    = (a.get("source_name") or a.get("source") or "").strip()
    summary   = (a.get("summary") or "").strip()
    image_url = (a.get("image_url") or "").strip()
    date      = _fmt_date(a.get("time", ""))
    is_reddit = a.get("source") == "reddit"

    meta_parts = []
    if source:
        meta_parts.append(f"<b>{source}</b>")
    if date:
        meta_parts.append(date)
    if is_reddit:
        meta_parts.append(f"⬆ {a.get('score', 0):,}  💬 {a.get('comments', 0):,}")
        if a.get("subreddit"):
            meta_parts.append(f"r/{a['subreddit']}")

    # Intelligence badges
    badge_html = ""
    iv = intel.get(a["id"]) if intel else None
    if iv:
        if iv.is_duplicate:
            badge_html += '<span class="badge badge-dupe">🔁 duplicate</span>'
        else:
            badge_html += _importance_badge(iv.importance)
            if iv.escalate:
                badge_html += '<span class="badge badge-red">🚨 breaking</span>'
            if iv.is_hype:
                badge_html += '<span class="badge badge-hype">⚠️ hype</span>'

    img_html = (
        f'<img src="{image_url}" onerror="this.style.display=\'none\'" />'
        if image_url else ""
    )
    summary_html = (summary[:280] + "…" if len(summary) > 280 else summary)

    st.markdown(f"""
<div class="card">
  {img_html}
  <div class="card-title"><a href="{url}" target="_blank">{title}</a></div>
  <div class="card-meta">{"  ·  ".join(meta_parts)}</div>
  {"<div style='margin:4px 0'>" + badge_html + "</div>" if badge_html else ""}
  {"<div class='card-body'>" + summary_html + "</div>" if summary_html else ""}
</div>
""", unsafe_allow_html=True)


def render_grid(
    articles: list[dict],
    intel: dict[str, ArticleIntel] | None = None,
    max_items: int = 40,
) -> None:
    if not articles:
        st.info("No articles loaded — check feed URLs or hit Refresh.")
        return
    items = _apply_sort(articles)[:max_items]
    for i in range(0, len(items), 2):
        left, right = st.columns(2, gap="medium")
        with left:
            render_article(items[i], intel)
        if i + 1 < len(items):
            with right:
                render_article(items[i + 1], intel)


# ── Alerts panel ──────────────────────────────────────────────────────────────

def render_alerts(articles: list[dict], intel: dict[str, ArticleIntel]) -> None:
    escalated = [
        a for a in articles
        if intel.get(a["id"]) and intel[a["id"]].escalate and not intel[a["id"]].is_duplicate
    ]
    if not escalated:
        return

    items_html = ""
    for a in escalated[:6]:
        iv = intel[a["id"]]
        t = (a.get("title") or "").replace('"', "&quot;")
        u = a.get("url") or "#"
        src = a.get("source_name") or a.get("source") or ""
        reason = iv.escalation_reason
        items_html += (
            f'<div class="alert-item">'
            f'[{iv.importance:.1f}] <a href="{u}" target="_blank">{t}</a>'
            f'<span style="color:#888"> — {src} · {reason}</span>'
            f'</div>'
        )

    st.markdown(
        f'<div class="alert-banner">'
        f'<h4>🚨 BREAKING / ESCALATED ({len(escalated)} items)</h4>'
        f'{items_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Sidebar: controls + Hermes chat ──────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚡ Hermes")
    st.caption("AI News Intelligence Agent")

    col_ref, col_sort = st.columns([1, 2])
    with col_ref:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("intel", None)
            st.rerun()
    with col_sort:
        st.selectbox(
            "Sort",
            ["Latest", "Hottest", "Top Scored"],
            key="sort_mode",
            label_visibility="collapsed",
        )

    st.divider()
    st.markdown("### 💬 Ask Hermes")
    st.caption("Pre-analyzes live data and gives a detailed briefing.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.container(height=360, border=False):
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_input = st.text_area(
        "question",
        placeholder="e.g. What's the biggest AI story today?",
        label_visibility="collapsed",
        height=80,
        key="hermes_input",
    )

    if st.button("Send", use_container_width=True, type="primary"):
        query = user_input.strip()
        if query:
            st.session_state.chat_history.append({"role": "user", "content": query})
            with st.spinner("Hermes is analyzing news…"):
                try:
                    answer = asyncio.run(run_hermes_agent(query))
                except Exception as exc:
                    answer = f"**Error:** {exc}"
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

    if st.session_state.chat_history:
        if st.button("Clear chat", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()


# ── Main feed ─────────────────────────────────────────────────────────────────

st.markdown("# AI News")
st.caption(
    f"{len(NEWSLETTER_FEEDS)} newsletters · "
    f"{len(MEDIA_FEEDS)} media · "
    f"{len(COMPANY_BLOG_FEEDS)} company blogs · "
    f"{len(RESEARCH_FEEDS)} research · "
    "Reddit · refreshes every 30 min"
)

with st.spinner("Loading feeds…"):
    newsletters   = load_newsletters()
    media         = load_media()
    company_blogs = load_company_blogs()
    research      = load_research()
    reddit        = load_reddit()

all_articles = newsletters + media + company_blogs + research + reddit

# Run intelligence pipeline once and cache in session state
if "intel" not in st.session_state:
    with st.spinner("Running intelligence pipeline…"):
        st.session_state.intel = analyze(all_articles)

intel = st.session_state.intel

# Alerts panel above tabs
render_alerts(all_articles, intel)

tab_all, tab_nl, tab_media_t, tab_blogs, tab_research, tab_reddit, tab_brief = st.tabs([
    f"🌐 All ({len(all_articles)})",
    f"📧 Newsletters ({len(newsletters)})",
    f"📰 Media ({len(media)})",
    f"🏢 Company Blogs ({len(company_blogs)})",
    f"🔬 Research ({len(research)})",
    f"💬 Reddit ({len(reddit)})",
    "🧠 Brief",
])

with tab_all:
    render_grid(all_articles, intel)

with tab_nl:
    render_grid(newsletters, intel)

with tab_media_t:
    render_grid(media, intel)

with tab_blogs:
    render_grid(company_blogs, intel)

with tab_research:
    render_grid(research, intel)

with tab_reddit:
    render_grid(reddit, intel)

with tab_brief:
    st.markdown("### Intelligence Brief")

    dupes     = sum(1 for v in intel.values() if v.is_duplicate)
    escalated = sum(1 for v in intel.values() if v.escalate and not v.is_duplicate)
    hype      = sum(1 for v in intel.values() if v.is_hype and not v.is_duplicate)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total articles", len(all_articles))
    c2.metric("Duplicates filtered", dupes)
    c3.metric("Escalated", escalated)
    c4.metric("Hype-flagged", hype)

    st.divider()

    # Top stories by importance (non-duplicate)
    top = sorted(
        [a for a in all_articles if not intel.get(a["id"], None) or not intel[a["id"]].is_duplicate],
        key=lambda x: intel.get(x["id"], type("_", (), {"importance": 0})()).importance,
        reverse=True,
    )[:15]

    st.markdown("#### Top Stories by Importance")
    for a in top:
        iv = intel.get(a["id"])
        if not iv or iv.importance < 3:
            break
        importance = iv.importance if iv else 0
        badge = _importance_badge(importance)
        flags = ""
        if iv and iv.escalate:
            flags += " 🚨"
        if iv and iv.is_hype:
            flags += " ⚠️"
        title = a.get("title") or "Untitled"
        url   = a.get("url") or "#"
        src   = a.get("source_name") or a.get("source") or ""
        summary = (a.get("summary") or "")[:200]
        st.markdown(
            f"{badge}{flags} **[{title}]({url})**  \n"
            f"<span style='font-size:0.75rem;color:#888'>{src}</span>  \n"
            f"<span style='font-size:0.8rem;color:#bbb'>{summary}</span>",
            unsafe_allow_html=True,
        )
        st.divider()

    # Cluster summary
    from collections import defaultdict
    clusters: dict[str, list[dict]] = defaultdict(list)
    for a in all_articles:
        iv = intel.get(a["id"])
        if iv and not iv.is_duplicate and iv.cluster_id:
            clusters[iv.cluster_id].append(a)

    multi_clusters = {k: v for k, v in clusters.items() if len(v) >= 2}
    if multi_clusters:
        st.markdown("#### Story Clusters")
        st.caption("Groups of related articles covering the same topic.")
        for cid, group in sorted(multi_clusters.items(), key=lambda x: -len(x[1]))[:8]:
            with st.expander(f"Cluster {cid} — {len(group)} related articles"):
                for a in group:
                    iv = intel.get(a["id"])
                    imp = f"{iv.importance:.1f}" if iv else "?"
                    title = a.get("title") or "Untitled"
                    url   = a.get("url") or "#"
                    src   = a.get("source_name") or a.get("source") or ""
                    st.markdown(f"- [{title}]({url}) `{imp}` *{src}*")
