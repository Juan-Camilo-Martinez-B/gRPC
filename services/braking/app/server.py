from __future__ import annotations

import logging
import time

from railway.ptc.v1 import common_pb2, braking_pb2_grpc

from ptc_common.config import settings
from ptc_common.db import Database, wait_for_db
from ptc_common.runtime import configure_logging, serve

from app.evaluation import evaluate, load_blocks

log = logging.getLogger("ptc.braking")

_SIGNALS = {
    "PROCEED": common_pb2.ControlCommandOutput.PROCEED,
    "CAUTION": common_pb2.ControlCommandOutput.CAUTION,
    "STOP": common_pb2.ControlCommandOutput.STOP,
    "EMERGENCY_BRAKE": common_pb2.ControlCommandOutput.EMERGENCY_BRAKE,
}


def _command(telemetry, result: dict) -> common_pb2.ControlCommandOutput:
    return common_pb2.ControlCommandOutput(
        train_id=telemetry.train_id,
        signal=_SIGNALS[result["signal"]],
        message=result["message"],
        timestamp=int(time.time() * 1000),
        sequence=telemetry.sequence,
        braking_distance_m=result["braking_distance_m"],
        distance_to_hazard_m=result["distance_to_hazard_m"],
        target_speed_kmh=result["target_speed_kmh"],
        hazard_block_id=result["hazard_block_id"],
    )


def _fail_safe(telemetry, reason: str) -> common_pb2.ControlCommandOutput:
    log.error("fail-safe de frenado para %s: %s", telemetry.train_id, reason)
    return common_pb2.ControlCommandOutput(
        train_id=telemetry.train_id,
        signal=common_pb2.ControlCommandOutput.EMERGENCY_BRAKE,
        message=f"Fail-safe: {reason}",
        timestamp=int(time.time() * 1000),
        sequence=telemetry.sequence,
        braking_distance_m=telemetry.current_braking_distance,
        distance_to_hazard_m=0,
        target_speed_kmh=0,
        hazard_block_id=telemetry.current_block_id,
    )


class BrakingServicer(braking_pb2_grpc.BrakingServiceServicer):
    def __init__(self, db: Database) -> None:
        self.db = db

    def _decide(self, telemetry):
        try:
            blocks = load_blocks(self.db)
            return _command(telemetry, evaluate(telemetry, blocks))
        except Exception as exc:  # noqa: BLE001 - fallo seguro
            return _fail_safe(telemetry, str(exc))

    def CalculateBrakingCurve(self, request, context):
        del context
        return self._decide(request)

    def StreamTelemetryAndControl(self, request_iterator, context):
        del context
        for telemetry in request_iterator:
            log.info(
                "stream rx %s seq=%s bloque=%s v=%.1f",
                telemetry.train_id,
                telemetry.sequence,
                telemetry.current_block_id,
                telemetry.speed_kmh,
            )
            yield self._decide(telemetry)


def main() -> None:
    configure_logging()
    cfg = settings()
    wait_for_db(cfg.database_url)
    db = Database(cfg.database_url, cfg.application_name)
    serve(
        braking_pb2_grpc.add_BrakingServiceServicer_to_server,
        BrakingServicer(db),
        cfg.port,
        "Braking Calculation Service",
    )


if __name__ == "__main__":
    main()
