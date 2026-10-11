#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt -r requirements-app.txt
fi

if [[ ! -f .env ]]; then
  .venv/bin/python init_local_env.py
fi

set -a
source .env
set +a

.venv/bin/python ../db/build_demo_db.py --quiet

api_log="/tmp/verdant_api_$$.log"
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port "${API_PORT:-8000}" >"$api_log" 2>&1 &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
  rm -f "$api_log"
}
trap cleanup EXIT INT TERM

for _ in {1..40}; do
  if curl --silent --fail "http://127.0.0.1:${API_PORT:-8000}/health" >/dev/null; then
    break
  fi
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "The API failed to start:"
    tail -n 30 "$api_log"
    exit 1
  fi
  sleep 0.25
done

.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port "${PORT:-8502}"
