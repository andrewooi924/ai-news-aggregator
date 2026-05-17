import asyncio
from mcp.server.fastmcp import FastMCP
from sources.reddit import fetch_reddit_ai, DEFAULT_SUBREDDITS
from sources.rss_fetcher import fetch_rss_ai, list_rss_sources, RSS_FEEDS, FEED_CATEGORIES

mcp = FastMCP("AI News Aggregator")


@mcp.tool()
async def get_ai_news(
    limit: int = 60,
    include_reddit: bool = True,
    include_rss: bool = True,
) -> list[dict]:
    """Aggregate AI news from Reddit and all RSS feeds (newsletters, media, company blogs, research).

    Args:
        limit: Maximum total items to return.
        include_reddit: Include Reddit posts.
        include_rss: Include all RSS feeds.
    """
    tasks = []
    if include_reddit:
        tasks.append(fetch_reddit_ai(limit_per_sub=5))
    if include_rss:
        tasks.append(fetch_rss_ai(limit_per_feed=3))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_items = [item for r in results if isinstance(r, list) for item in r]
    all_items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_items[:limit]


@mcp.tool()
async def get_reddit_ai(
    subreddits: list[str] | None = None,
    limit_per_sub: int = 10,
) -> list[dict]:
    """Fetch hot posts from AI-focused subreddits.

    Args:
        subreddits: Subreddit names. Defaults to all configured subreddits.
        limit_per_sub: Posts per subreddit.
    """
    return await fetch_reddit_ai(subreddits=subreddits, limit_per_sub=limit_per_sub)


@mcp.tool()
async def get_rss_ai_news(
    feeds: list[str] | None = None,
    category: str | None = None,
    limit_per_feed: int = 10,
) -> list[dict]:
    """Fetch AI news from RSS feeds across newsletters, media, company blogs, and research sources.

    Args:
        feeds: Specific feed keys to fetch. If omitted, fetches all (or all in category).
        category: Filter by category: newsletter, media, company_blog, research.
        limit_per_feed: Articles per feed.
    """
    return await fetch_rss_ai(feeds=feeds, category=category, limit_per_feed=limit_per_feed)


@mcp.tool()
async def list_available_sources() -> dict:
    """List all available news sources with their feed keys and categories."""
    return {
        "reddit": {"description": "Hot posts from AI subreddits", "subreddits": DEFAULT_SUBREDDITS},
        "rss_feeds": list_rss_sources(),
    }


if __name__ == "__main__":
    mcp.run()
