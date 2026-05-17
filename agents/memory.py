"""
Persistent memory for Hermes — tracks seen articles and session history.
Stored as a local JSON file so novelty scoring works across restarts.
"""
import json
import os
from datetime import datetime
from typing import Any

from agents.intelligence import ArticleIntel

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "hermes_memory.json")


class HermesMemory:
    def __init__(self, path: str = MEMORY_PATH):
        self.path = os.path.abspath(path)
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"seen_urls": {}, "sessions": []}

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    def novelty(self, url: str) -> float:
        """1.0 = never seen before, decays to 0.0 after 48 hours."""
        entry = self._data["seen_urls"].get(url)
        if not entry:
            return 1.0
        try:
            first = datetime.fromisoformat(entry["first_seen"])
            hours = (datetime.now() - first).total_seconds() / 3600
            return max(0.0, round(1.0 - hours / 48, 2))
        except Exception:
            return 0.0

    def mark_seen(self, articles: list[dict], intel: dict[str, ArticleIntel]) -> None:
        now = datetime.now().isoformat()
        for a in articles:
            url = a.get("url", "")
            if not url or url in self._data["seen_urls"]:
                continue
            iv = intel.get(a["id"])
            self._data["seen_urls"][url] = {
                "first_seen": now,
                "importance": iv.importance if iv else 0.0,
                "title": a.get("title", "")[:120],
            }
        # Keep last 10 000 entries
        if len(self._data["seen_urls"]) > 10_000:
            items = sorted(
                self._data["seen_urls"].items(),
                key=lambda x: x[1].get("first_seen", ""),
            )
            self._data["seen_urls"] = dict(items[-10_000:])
        self._save()

    def add_session(self, brief_summary: str, stats: dict) -> None:
        self._data["sessions"].append({
            "timestamp": datetime.now().isoformat(),
            "summary": brief_summary[:400],
            **stats,
        })
        self._data["sessions"] = self._data["sessions"][-100:]
        self._save()

    def recent_sessions(self, n: int = 5) -> list[dict]:
        return self._data["sessions"][-n:]

    @property
    def total_seen(self) -> int:
        return len(self._data["seen_urls"])
