import asyncio
import httpx
from datetime import datetime
from typing import Any

BASE_URL = "https://hacker-news.firebaseio.com/v0"
AI_KEYWORDS = {
    "ai", "llm", "gpt", "claude", "gemini", "llama", "transformer",
    "openai", "anthropic", "deepmind", "machine learning", "deep learning",
    "neural", "diffusion", "stable diffusion", "midjourney", "dall-e",
    "reinforcement learning", "rlhf", "fine-tun", "embedding", "vector",
    "chatbot", "large language", "foundation model", "multimodal",
    "mistral", "falcon", "hugging face", "langchain", "autonomous agent",
    "retrieval augmented", "rag", "inference", "quantization", "lora",
    "artificial intelligence", "generative ai", "genai", "sora", "gemma",
    "ollama", "vllm", "tts", "whisper", "speech", "copilot", "cursor"
}


def _is_ai_related(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in AI_KEYWORDS)


async def fetch_story(client: httpx.AsyncClient, story_id: int) -> dict[str, Any] | None:
    try:
        r = await client.get(f"{BASE_URL}/item/{story_id}.json", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        if not data or data.get("type") != "story" or not data.get("title"):
            return None
        return data
    except Exception:
        return None


async def fetch_hackernews_ai(limit: int = 30) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/topstories.json", timeout=10.0)
        r.raise_for_status()
        top_ids = r.json()[:200]

        tasks = [fetch_story(client, sid) for sid in top_ids]
        stories = await asyncio.gather(*tasks)

    ai_stories = []
    for s in stories:
        if s and _is_ai_related(s.get("title", "")):
            ai_stories.append({
                "id": str(s["id"]),
                "title": s["title"],
                "url": s.get("url", f"https://news.ycombinator.com/item?id={s['id']}"),
                "score": s.get("score", 0),
                "comments": s.get("descendants", 0),
                "by": s.get("by", "unknown"),
                "time": datetime.fromtimestamp(s.get("time", 0)).isoformat(),
                "source": "hacker_news",
            })

    ai_stories.sort(key=lambda x: x["score"], reverse=True)
    return ai_stories[:limit]
