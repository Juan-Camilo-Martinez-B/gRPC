#!/bin/sh
set -eu

python3 - <<'PY'
from pathlib import Path
import os

template = Path("/etc/envoy/envoy.yaml.template").read_text()
rendered = template.replace("__LISTEN_PORT__", os.environ.get("PORT", "8080"))
rendered = rendered.replace(
    "__CORS_ORIGIN__",
    os.environ.get("CORS_ORIGIN", "https://g-rpc-one.vercel.app"),
)
Path("/etc/envoy/envoy.yaml").write_text(rendered)
PY

python3 /app/deploy/bootstrap.py

start_service() {
  directory="$1"
  port="$2"
  name="$3"
  (
    cd "$directory"
    PORT="$port" APPLICATION_NAME="$name" python3 -m app.server
  ) &
}

start_service /app/services/track 50052 ptc-track
start_service /app/services/braking 50053 ptc-braking
start_service /app/services/telemetry 50054 ptc-telemetry
start_service /app/services/simulation 50051 ptc-simulation
start_service /app/services/dispatch 50055 ptc-dispatch

trap 'kill $(jobs -p) 2>/dev/null || true' INT TERM

exec envoy -c /etc/envoy/envoy.yaml --log-level info
