#!/usr/bin/env bash
# ──────────────────────────────────────────────────
#  InstaBot — Quick start script
# ──────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Create .env if missing
if [ ! -f .env ]; then
  echo "⚠  .env not found — copying from .env.example"
  cp .env.example .env
  echo "📝 Edit .env and fill in your MINIMAX keys, then run this script again."
  exit 1
fi

# 2. Create virtual env if missing
if [ ! -d .venv ]; then
  echo "🐍 Creating virtual environment…"
  python3 -m venv .venv
fi

# 3. Activate venv
source .venv/bin/activate

# 4. Install/update dependencies
echo "📦 Installing dependencies…"
pip install -q -r requirements.txt

# 5. Launch
echo ""
echo "🚀 Starting InstaBot Dashboard…"
echo "   Open: http://localhost:8000"
echo ""

python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
