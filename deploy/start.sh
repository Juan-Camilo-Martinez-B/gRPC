#!/bin/sh
set -eu

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
