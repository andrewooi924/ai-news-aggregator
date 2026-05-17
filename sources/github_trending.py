import os
from datetime import datetime, timedelta
from typing import Any
import httpx

GITHUB_API = "https://api.github.com/search/repositories"
BASE_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "AI-News-Aggregator/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}
AI_QUERY = (
    "topic:llm OR topic:large-language-model OR topic:artificial-intelligence "
    "OR topic:machine-learning OR topic:generative-ai OR topic:llm-inference"
)


async def fetch_github_trending(limit: int = 20) -> list[dict[str, Any]]:
    since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    headers = {**BASE_HEADERS}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "q": f"({AI_QUERY}) pushed:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 30),
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(GITHUB_API, params=params, headers=headers, timeout=10.0)
        r.raise_for_status()
        data = r.json()

    results = []
    for repo in data.get("items", []):
        stars = repo.get("stargazers_count", 0)
        results.append({
            "id": str(repo["id"]),
            "title": f"{repo['full_name']}  ★ {stars:,}",
            "url": repo["html_url"],
            "summary": repo.get("description") or "",
            "stars": stars,
            "score": stars,
            "language": repo.get("language") or "",
            "by": repo["full_name"].split("/")[0],
            "time": repo.get("pushed_at", ""),
            "source": "github_trending",
            "source_name": "GitHub Trending",
            "category": "community",
        })
    return results
