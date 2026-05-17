# ⚡ AI News MCP Agent with Hermes3

An MCP (Model Context Protocol) server that aggregates live AI news from Reddit, newsletters, media outlets, company blogs, and research sources — and makes it available as tools directly inside Claude Desktop.

A standalone Streamlit dashboard with an AI chat agent powered by a local Ollama model.

---

## Features

- **MCP server** — plug directly into Claude Desktop; ask Claude for AI news and it fetches live results
- **4 MCP tools** — aggregate all sources, filter by Reddit, filter by RSS category or list available sources
- **Intelligence pipeline** — automatic deduplication, importance scoring (0–10), hype detection, story clustering and breaking news escalation
- **Rich source coverage** across 4 categories:
  - 📧 **Newsletters** — The Rundown AI, Ben's Bites, TLDR AI, Latent Space, Import AI, The Batch and more
  - 📰 **Media** — TechCrunch, The Verge, Wired, MIT Technology Review, VentureBeat, Ars Technica and more
  - 🏢 **Company blogs** — OpenAI, Anthropic, Google DeepMind, Meta AI, Hugging Face, Mistral, NVIDIA
  - 🔬 **Research** — arXiv AI papers, GitHub Trending
  - 💬 **Reddit** — r/MachineLearning, r/artificial, r/LocalLLaMA and other AI subreddits
- **Streamlit dashboard** — visual card-based feed with tabs per source category, sort modes, alerts panel and story clusters
- **Hermes chat agent** — sidebar chat powered by a local Ollama model (default: `hermes3`) that pre-fetches and analyses the news before answering

---

## Project Structure

```
MCP-AI-NEWS-AGENT/
├── server.py                  # MCP server (Claude Desktop integration)
├── app.py                     # Streamlit dashboard
├── hermes_agent.py            # Ollama-powered chat agent
├── agents/
│   ├── intelligence.py        # Scoring, deduplication, clustering, hype detection
│   └── memory.py              # Agent memory
├── sources/
│   ├── rss_fetcher.py         # Newsletters, media, company blogs, research feeds
│   ├── reddit.py              # Reddit AI subreddits
│   ├── arxiv_fetcher.py       # arXiv research papers
│   └── github_trending.py     # GitHub Trending repositories
├── .env.example               # Environment variable template
├── requirements.txt
└── claude_desktop_config.json # Claude Desktop config reference
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/MCP-AI-NEWS-AGENT.git
cd MCP-AI-NEWS-AGENT
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required for Hermes Streamlit agent (local or RunPod Ollama)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=hermes3

# Optional — raises GitHub API rate limit from 60 to 5000 req/hour
GITHUB_TOKEN=your_token_here
```

---

## Option A — Claude Desktop (MCP Server)

This connects the news agent directly to Claude Desktop so you can ask Claude for live AI news.

### 1. Edit `claude_desktop_config.json`

Update the paths to match your system, then copy it to the Claude Desktop config location:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ai-news-aggregator": {
      "command": "/path/to/your/python",
      "args": ["/path/to/MCP-AI-NEWS-AGENT/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/MCP-AI-NEWS-AGENT"
      }
    }
  }
}
```

> **Tip:** Use the absolute path to your Python binary (`which python3` on macOS/Linux). If you use Anaconda, it will be something like `/opt/anaconda3/bin/python`.

### 2. Restart Claude Desktop

Fully quit (Cmd+Q on Mac) and reopen. In the **Chat** tab, open a conversation and look for the 🔨 hammer icon in the input toolbar — that confirms your tools are connected.

### Available MCP tools

| Tool | Description |
|---|---|
| `get_ai_news` | Aggregate AI news from all sources (Reddit + RSS) |
| `get_reddit_ai` | Fetch hot posts from AI subreddits |
| `get_rss_ai_news` | Fetch from RSS feeds, optionally filtered by category |
| `list_available_sources` | List all configured sources and feed keys |

### Example prompts

- *"What are the top AI stories today?"*
- *"What's trending on the AI subreddits right now?"*
- *"Show me the latest AI research papers"*
- *"Any breaking AI news from company blogs?"*

---

## Option B — Streamlit Dashboard

Run the visual dashboard locally in your browser:

```bash
streamlit run app.py
```

The dashboard includes:
- Tabbed feed by source category (All, Newsletters, Media, Company Blogs, Research, Reddit)
- Sort by Latest, Hottest, or Top Scored
- Intelligence badges: importance score, 🚨 breaking, ⚠️ hype, 🔁 duplicate
- Alerts panel for escalated/breaking stories
- Intelligence Brief tab with top stories and story clusters
- **Hermes chat sidebar** — ask questions about the current news feed

> The Hermes agent requires a running Ollama instance with your chosen model pulled (`ollama pull hermes3`). For remote use, set `OLLAMA_BASE_URL` to a RunPod or similar endpoint in your `.env`.

---

## Intelligence Pipeline

Before displaying or answering questions, all articles are processed by a programmatic intelligence layer (`agents/intelligence.py`):

- **Deduplication** — cosine-similarity clustering removes near-duplicate stories across sources
- **Importance scoring** — 0–10 score based on source tier, keyword matching, and recency
- **Hype detection** — flags articles using unsubstantiated superlatives
- **Escalation** — surfaces breaking stories (major model releases, funding, regulation, security incidents)
- **Story clustering** — groups related articles covering the same event

---

## Requirements

- Python 3.10+
- Ollama (for the Streamlit agent only — not needed for the MCP server)
- Claude Desktop (for MCP integration)

---

## License

MIT