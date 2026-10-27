#!/usr/bin/env bash
# Local dev database: Postgres 18 + pgvector in Docker, on localhost:5433.
# Usage: scripts/dev_db.sh up|down
# The data lives in a named volume, so `down` then `up` keeps it.
set -euo pipefail

NAME=ayo-dev-db
VOLUME=ayo-dev-db-data
# Same image as the integration tests (tests/integration/support.py).
IMAGE=pgvector/pgvector:0.8.7-pg18-trixie
PORT=5433

case "${1:-}" in
  up)
    if [ -n "$(docker ps -q --filter "name=^${NAME}$")" ]; then
      echo "${NAME} is already running"
    elif [ -n "$(docker ps -aq --filter "name=^${NAME}$")" ]; then
      docker start "${NAME}" >/dev/null
    else
      # Postgres 18 images keep their data under /var/lib/postgresql/18/docker.
      docker run -d --name "${NAME}" \
        -e POSTGRES_USER=ayo -e POSTGRES_PASSWORD=ayo -e POSTGRES_DB=ayo \
        -p "127.0.0.1:${PORT}:5432" \
        -v "${VOLUME}:/var/lib/postgresql" \
        "${IMAGE}" >/dev/null
    fi
    for _ in $(seq 1 30); do
      if docker exec "${NAME}" pg_isready -U ayo -d ayo -q; then
        echo "ready: postgresql://ayo:ayo@localhost:${PORT}/ayo"
        exit 0
      fi
      sleep 1
    done
    echo "${NAME} did not become ready in 30 s; see: docker logs ${NAME}" >&2
    exit 1
    ;;
  down)
    if [ -n "$(docker ps -q --filter "name=^${NAME}$")" ]; then
      docker stop "${NAME}" >/dev/null
      echo "${NAME} stopped"
    else
      echo "${NAME} is not running"
    fi
    ;;
  *)
    echo "usage: $0 up|down" >&2
    exit 2
    ;;
esac
