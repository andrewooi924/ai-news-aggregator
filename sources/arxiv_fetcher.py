import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
import httpx

BASE_URL = "http://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = ["cs.AI", "cs.LG", "cs.CV", "cs.CL", "cs.NE", "cs.RO", "stat.ML"]
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        summary_el = entry.find("atom:summary", NS)
        id_el = entry.find("atom:id", NS)
        published_el = entry.find("atom:published", NS)

        title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""
        summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None else ""
        arxiv_id = id_el.text.strip() if id_el is not None else ""
        published = published_el.text.strip() if published_el is not None else ""

        authors = [
            a.find("atom:name", NS).text
            for a in entry.findall("atom:author", NS)
            if a.find("atom:name", NS) is not None
        ]
        categories = [
            t.get("term", "") for t in entry.findall("atom:category", NS)
        ]
        links = {lnk.get("title", "html"): lnk.get("href", "") for lnk in entry.findall("atom:link", NS)}

        entries.append({
            "id": arxiv_id.split("/abs/")[-1] if "/abs/" in arxiv_id else arxiv_id,
            "title": title,
            "url": links.get("html", arxiv_id),
            "pdf_url": links.get("pdf", ""),
            "authors": authors[:5],
            "summary": summary[:500] + ("..." if len(summary) > 500 else ""),
            "categories": categories,
            "time": published,
            "source": "arxiv",
        })
    return entries


async def fetch_arxiv_ai(
    categories: list[str] | None = None,
    max_results: int = 20,
    search_query: str = "",
) -> list[dict[str, Any]]:
    cats = categories or DEFAULT_CATEGORIES
    cat_query = " OR ".join(f"cat:{c}" for c in cats)
    query = f"({cat_query})"
    if search_query:
        query = f"({search_query}) AND {query}"

    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(BASE_URL, params=params, timeout=15.0)
        r.raise_for_status()

    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _parse_arxiv_feed, r.text)
    return entries
