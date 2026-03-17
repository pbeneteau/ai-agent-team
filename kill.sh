#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

declare -a KILLED_PIDS=()

add_pid() {
  local pid="$1"

  if [[ -z "${pid}" ]]; then
    return
  fi

  for existing in "${KILLED_PIDS[@]:-}"; do
    if [[ "${existing}" == "${pid}" ]]; then
      return
    fi
  done

  KILLED_PIDS+=("${pid}")
}

find_matching_pids() {
  local pattern="$1"

  ps -ax -o pid= -o command= | awk -v pattern="${pattern}" '
    index($0, pattern) > 0 {
      print $1
    }
  '
}

collect_server_pids() {
  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(find_matching_pids "${ROOT_DIR}/backend/.venv/bin/uvicorn")

  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(find_matching_pids "uvicorn app.main:app --host 127.0.0.1 --port 8000")

  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(find_matching_pids "${ROOT_DIR}/frontend/node_modules/.bin/next")

  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(find_matching_pids "next dev")

  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(lsof -ti tcp:8000 2>/dev/null || true)

  while IFS= read -r pid; do
    add_pid "${pid}"
  done < <(lsof -ti tcp:3000 2>/dev/null || true)
}

terminate_pid() {
  local pid="$1"

  if ! kill -0 "${pid}" 2>/dev/null; then
    return
  fi

  echo "Stopping PID ${pid}..."
  kill "${pid}" 2>/dev/null || true

  for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return
    fi
    sleep 1
  done

  if kill -0 "${pid}" 2>/dev/null; then
    echo "Force killing PID ${pid}..."
    kill -9 "${pid}" 2>/dev/null || true
  fi
}

main() {
  echo "Looking for running project servers..."
  collect_server_pids

  if [[ "${#KILLED_PIDS[@]}" -eq 0 ]]; then
    echo "No matching backend/frontend server process found."
    exit 0
  fi

  for pid in "${KILLED_PIDS[@]}"; do
    terminate_pid "${pid}"
  done

  echo "Done."
}

main "$@"
