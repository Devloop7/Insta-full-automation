# InstaBot — Full Instagram Automation

A complete Instagram growth bot with a web dashboard.

## What it does

| Feature | Description |
|---|---|
| **Content Harvesting** | Scrapes Reels, Posts & Stories from up to N source accounts |
| **AI Captions** | Rewrites captions using MiniMax AI, tuned to your niche |
| **Auto Posting** | Posts to your account on a customizable schedule |
| **AI Agent** | Likes & comments on niche content automatically |
| **Smart Comments** | MiniMax generates genuine, niche-aware comments (not spam) |
| **Dashboard UI** | Full web UI to control everything |
| **Rate limiting** | Built-in delays & daily limits to avoid bans |

---

## Quick Start

```bash
# 1. Clone / enter the directory
cd Insta-full-automation

# 2. Run (creates venv + installs deps automatically)
chmod +x run.sh
./run.sh

# 3. Open the dashboard
open http://localhost:8000
```

On first run, a `.env` file is created from `.env.example`.
Fill in your **MiniMax API key** and **Group ID**, then run again.

---

## Setup walkthrough

### 1. Add your target account
Go to **Accounts → Add Account**
Enter your Instagram username, password, and niche details.
Click **Login** to test the connection.

### 2. Add source accounts
Go to **Source Accounts → Add Source**
Add the 3 (or more) accounts you want to re-post content from.
Choose what to scrape: Reels / Posts / Stories.

### 3. Set your niche
In the target account settings, set:
- **Niche**: e.g. `fitness`, `crypto`, `cooking`
- **Keywords**: `gym,workout,bodybuilding,protein`
- **Description**: full description of your audience for the AI

### 4. Create a schedule
Go to **Scheduler → New Schedule**
Configure:
- Scrape interval (how often to check source accounts)
- Post times (when to post each day)
- AI Agent interval (how often to like/comment)

### 5. Start the scheduler
Click **Start Scheduler** — the bot runs fully automated from here.

---

## Manual controls (Dashboard quick-actions)
- **Scrape** — fetch new content from sources right now
- **Pipeline** — scrape + download + generate captions + post in one go
- **Post Now** — immediately post the next queued item
- **Agent** tab — run a like/comment session manually

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `MINIMAX_API_KEY` | — | Your MiniMax API key |
| `MINIMAX_GROUP_ID` | — | Your MiniMax Group ID |
| `MINIMAX_MODEL` | `abab6.5s-chat` | MiniMax model to use |
| `INSTAGRAM_DELAY_MIN` | `30` | Min seconds between actions |
| `INSTAGRAM_DELAY_MAX` | `120` | Max seconds between actions |
| `MAX_LIKES_PER_HOUR` | `30` | Like rate limit |
| `MAX_COMMENTS_PER_HOUR` | `10` | Comment rate limit |
| `MAX_POSTS_PER_DAY` | `6` | Max posts per day |
| `PORT` | `8000` | Dashboard port |

---

## Architecture

```
backend/
├── main.py                   FastAPI app + static serving
├── core/
│   ├── config.py             Settings from .env
│   └── scheduler.py          APScheduler engine
├── models/
│   ├── database.py           SQLAlchemy models (SQLite)
│   └── schemas.py            Pydantic request/response schemas
├── routers/
│   ├── accounts.py           Target & source account CRUD
│   ├── content.py            Content queue + pipeline triggers
│   ├── agent.py              AI agent manual run + logs
│   ├── scheduler_router.py   Schedule CRUD + start/stop
│   └── logs.py               Activity log viewer
└── services/
    ├── instagram.py          instagrapi wrapper (login, scrape, upload)
    ├── minimax.py            MiniMax API client (comments, captions)
    ├── content_pipeline.py   Scrape → Download → Caption → Post
    └── ai_agent.py           Auto like/comment engine

frontend/
└── index.html                Full SPA (Tailwind + Alpine.js)
```

---

## ⚠️ Disclaimer
Use responsibly. Automation violates Instagram's Terms of Service.
Keep limits conservative. Use at your own risk.
