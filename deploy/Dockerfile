FROM envoyproxy/envoy:v1.32.3

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY proto /proto
COPY shared/python /app/shared/python
COPY db/init.sql /app/db/init.sql
COPY services/track/app /app/services/track/app
COPY services/braking/app /app/services/braking/app
COPY services/telemetry/app /app/services/telemetry/app
COPY services/dispatch/app /app/services/dispatch/app
COPY services/simulation/app /app/services/simulation/app
COPY deploy/bootstrap.py /app/deploy/bootstrap.py
COPY deploy/start.sh /app/deploy/start.sh
COPY deploy/envoy.prod.yaml /etc/envoy/envoy.yaml

RUN mkdir -p /app/gen \
    && python3 -m grpc_tools.protoc \
      -I /proto \
      --python_out=/app/gen \
      --grpc_python_out=/app/gen \
      /proto/railway/ptc/v1/common.proto \
      /proto/railway/ptc/v1/track.proto \
      /proto/railway/ptc/v1/braking.proto \
      /proto/railway/ptc/v1/telemetry.proto \
      /proto/railway/ptc/v1/dispatch.proto \
      /proto/railway/ptc/v1/simulation.proto \
    && python3 -c "import pathlib; root=pathlib.Path('/app/gen'); [path.joinpath('__init__.py').touch() for path in [root, *root.rglob('*')] if path.is_dir()]" \
    && chmod +x /app/deploy/start.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/gen:/app/shared/python \
    TRACK_ADDR=127.0.0.1:50052 \
    BRAKING_ADDR=127.0.0.1:50053 \
    TELEMETRY_ADDR=127.0.0.1:50054 \
    DISPATCH_ADDR=127.0.0.1:50055 \
    SIMULATION_ADDR=127.0.0.1:50051 \
    DB_POOL_MAX=2 \
    TICK_SECONDS=1.0

EXPOSE 8080
CMD ["/app/deploy/start.sh"]
