#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
VENV_DIR="${VENV_DIR:-venv}"
LOG_DIR="${LOG_DIR:-data}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/sinometa-server.log}"

mkdir -p "$LOG_DIR"

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    echo "Python is not installed or not in PATH." >&2
    exit 1
  fi
}

ensure_venv() {
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    PYTHON_BIN="$(find_python)"
    echo "Creating virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  "$VENV_DIR/bin/python" -m pip install -U pip
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
}

stop_port() {
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$PORT" || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$PORT"/tcp 2>/dev/null || true)"
  fi

  if [ -n "$pids" ]; then
    echo "Stopping existing process(es) on port $PORT: $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    kill -9 $pids 2>/dev/null || true
  fi
}

start_server() {
  echo "Starting SinoMeta"
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"
  exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT"
}

start_daemon() {
  stop_port
  echo "Starting SinoMeta in background"
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"
  nohup "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
  echo "PID: $!"
}

case "${1:-start}" in
  start)
    ensure_venv
    stop_port
    start_server
    ;;
  daemon)
    ensure_venv
    start_daemon
    ;;
  stop)
    stop_port
    ;;
  restart)
    ensure_venv
    stop_port
    start_daemon
    ;;
  *)
    echo "Usage: ./start.sh [start|daemon|stop|restart]"
    echo "Env: HOST=0.0.0.0 PORT=8001 VENV_DIR=venv LOG_FILE=data/sinometa-server.log"
    exit 1
    ;;
esac
