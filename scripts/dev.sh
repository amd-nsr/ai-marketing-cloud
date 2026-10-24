#!/usr/bin/env bash
# Run the whole stack natively in one terminal: PostgreSQL and Redis in Docker, then the
# Django API, Celery worker, Celery beat and the Next.js dev server with prefixed output.
# Ctrl+C stops every process this script started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

colors=(36 33 35 32)  # cyan, yellow, magenta, green
names=(api worker beat web)
pids=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping…"
  for pid in "${pids[@]}"; do
    # Each service runs in its own process group so its children stop too.
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Stopped. PostgreSQL and Redis keep running (make down to stop them)."
}
trap cleanup INT TERM EXIT

run() {
  local i=$1
  shift
  local prefix
  prefix=$(printf '\033[%sm%-6s|\033[0m' "${colors[$i]}" "${names[$i]}")
  # setsid: new process group, so cleanup can stop the whole tree.
  setsid bash -c "$* 2>&1 | sed -u 's/^/$prefix /'" &
  pids+=("$!")
}

test -f .env || { cp .env.example .env && echo "Created .env from .env.example"; }

echo "Starting PostgreSQL and Redis…"
docker compose up -d --wait postgres redis

echo "Applying migrations…"
(cd backend && uv run python manage.py migrate --noinput)

echo "Seeding demo users…"
(cd backend && uv run python manage.py seed_demo >/dev/null)

run 0 "cd backend && exec uv run python manage.py runserver 8000"
run 1 "cd backend && exec uv run celery -A config worker --loglevel=INFO"
run 2 "cd backend && exec uv run celery -A config beat --loglevel=INFO -s /tmp/amc-celerybeat-schedule"
run 3 "cd frontend && exec npm run dev"

echo "App: http://localhost:3000  ·  API: http://localhost:8000/api/v1/  ·  Demo logins: see README  ·  Ctrl+C to stop"

# Exit (and stop everything) as soon as any service dies.
wait -n
echo "A service exited; stopping the rest."
