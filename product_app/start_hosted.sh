#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

api_port="${API_PORT:-8000}"
web_port="${PORT:-8502}"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:${api_port}}"

api_log="/tmp/verdant_hosted_api_$$.log"
python -m uvicorn api:app --host 127.0.0.1 --port "$api_port" >"$api_log" 2>&1 &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
  rm -f "$api_log"
}
trap cleanup EXIT INT TERM

for _ in {1..80}; do
  if curl --silent --fail "http://127.0.0.1:${api_port}/health" >/dev/null; then
    break
  fi
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "The API failed to start:"
    tail -n 40 "$api_log"
    exit 1
  fi
  sleep 0.25
done

if ! curl --silent --fail "http://127.0.0.1:${api_port}/health" >/dev/null; then
  echo "The API did not become healthy before the startup deadline."
  tail -n 40 "$api_log"
  exit 1
fi

python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "$web_port" \
  --server.headless true \
  --browser.gatherUsageStats false
