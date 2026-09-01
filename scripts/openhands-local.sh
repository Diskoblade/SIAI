#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.openhands.yml"
ENV_FILE="$ROOT_DIR/backend/.env"
OPENHANDS_IMAGE="${OPENHANDS_IMAGE:-ghcr.io/openhands/agent-canvas:1.8.0}"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

remove_managed_runtimes() {
  local containers
  containers="$(docker ps -aq --filter label=sih.openhands.managed=true)"
  if [[ -n "$containers" ]]; then
    docker rm -f $containers
  fi
}

case "${1:-}" in
  start)
    docker pull "$OPENHANDS_IMAGE"
    compose up -d --build
    compose ps
    ;;
  stop)
    remove_managed_runtimes
    compose down
    ;;
  restart)
    remove_managed_runtimes
    compose down
    docker pull "$OPENHANDS_IMAGE"
    compose up -d --build
    compose ps
    ;;
  status)
    compose ps
    docker ps -a \
      --filter label=sih.openhands.managed=true \
      --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
    ;;
  logs)
    compose logs -f openhands-provisioner
    ;;
  *)
    printf 'Usage: %s {start|stop|restart|status|logs}\n' "$0" >&2
    exit 2
    ;;
esac
