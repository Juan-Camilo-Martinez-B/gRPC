FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/gen:/app

WORKDIR /app

COPY services/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY proto /proto
COPY shared/python/ptc_common /app/ptc_common

RUN mkdir -p /app/gen \
    && python -m grpc_tools.protoc \
      -I /proto \
      --python_out=/app/gen \
      --grpc_python_out=/app/gen \
      /proto/railway/ptc/v1/common.proto \
      /proto/railway/ptc/v1/track.proto \
      /proto/railway/ptc/v1/braking.proto \
      /proto/railway/ptc/v1/telemetry.proto \
      /proto/railway/ptc/v1/dispatch.proto \
      /proto/railway/ptc/v1/simulation.proto \
    && python -c "import pathlib; root=pathlib.Path('/app/gen'); [path.joinpath('__init__.py').touch() for path in [root, *root.rglob('*')] if path.is_dir()]"

COPY services/dispatch/app /app/app

ENV PORT=50055 \
    APPLICATION_NAME=ptc-dispatch
EXPOSE 50055
CMD ["python", "-m", "app.server"]
