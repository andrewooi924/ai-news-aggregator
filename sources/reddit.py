import asyncio
import html as html_mod
import httpx
from datetime import datetime
from typing import Any

HEADERS = {"User-Agent": "AI-News-Aggregator/1.0 (MCP Server)"}
DEFAULT_SUBREDDITS = [
    "MachineLearning", "artificial", "ChatGPT", "LocalLLaMA", "OpenAI",
    "StableDiffusion", "singularity", "AIAssistants", "deeplearning", "datascience",
]


async def fetch_subreddit(
    client: httpx.AsyncClient, subreddit: str, limit: int
) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        r = await client.get(url, headers=HEADERS, timeout=10.0)
        r.raise_for_status()
        posts = r.json()["data"]["children"]
        results = []
        for p in posts:
            d = p["data"]
            if d.get("stickied"):
                continue
            url_val = d.get("url", "")
            if url_val.startswith("/r/"):
                url_val = f"https://www.reddit.com{url_val}"

            # Best available image: high-res preview > thumbnail
            image_url = ""
            preview_images = d.get("preview", {}).get("images", [])
            if preview_images:
                src = preview_images[0].get("source", {}).get("url", "")
                if src:
                    image_url = html_mod.unescape(src)
            if not image_url:
                thumb = d.get("thumbnail", "")
                if thumb and thumb.startswith("http"):
                    image_url = thumb

            results.append({
                "id": d["id"],
                "title": d["title"],
                "url": url_val,
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "by": d.get("author", "unknown"),
                "subreddit": subreddit,
                "time": datetime.fromtimestamp(d.get("created_utc", 0)).isoformat(),
                "source": "reddit",
                "flair": d.get("link_flair_text", ""),
                "image_url": image_url,
            })
        return results
    except Exception:
        return []


async def fetch_reddit_ai(
    subreddits: list[str] | None = None, limit_per_sub: int = 10
) -> list[dict[str, Any]]:
    subs = subreddits or DEFAULT_SUBREDDITS
    async with httpx.AsyncClient() as client:
        tasks = [fetch_subreddit(client, sub, limit_per_sub) for sub in subs]
        results = await asyncio.gather(*tasks)

    all_posts = [post for sub_posts in results for post in sub_posts]
    all_posts.sort(key=lambda x: x["score"], reverse=True)
    return all_posts
