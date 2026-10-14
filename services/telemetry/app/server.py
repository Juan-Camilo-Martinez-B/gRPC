from __future__ import annotations

import logging
import time

import psycopg
from psycopg.rows import dict_row
from railway.ptc.v1 import common_pb2, telemetry_pb2, telemetry_pb2_grpc

from ptc_common.config import settings
from ptc_common.db import Database, wait_for_db
from ptc_common.runtime import configure_logging, serve

from app.repository import ingest_batch, load_railroad_state, record_safety_event

log = logging.getLogger("ptc.telemetry")


def _train_message(row: dict) -> common_pb2.TrainInfo:
    return common_pb2.TrainInfo(
        train_id=row["train_id"],
        speed=float(row["speed_kmh"]),
        block_id=row["current_block_id"] or "",
        status=row["status"],
        name=row["name"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        position_m=float(row["position_m"]),
        signal=row["signal"],
        braking_distance_m=float(row["braking_distance_m"]),
        adhesion_factor=float(row["adhesion_factor"]),
        manual_hold=bool(row["manual_hold"]),
        kind=row["kind"],
        distance_to_hazard_m=float(row["distance_to_hazard_m"]),
    )


def _block_message(row: dict) -> common_pb2.BlockInfo:
    occupier = row["occupied_by_train_id"] or ""
    return common_pb2.BlockInfo(
        block_id=row["block_id"],
        is_occupied=row["status"] == "OCCUPIED" and bool(occupier),
        occupied_by_train_id=occupier,
        status=row["status"],
        line_id=row["line_id"],
        sequence=int(row["sequence_order"]),
        signal_aspect=row["signal_aspect"],
        grade_percent=float(row["grade_percent"]),
        length_m=float(row["length_m"]),
        switch_position=row["switch_position"],
        latitude_start=float(row["latitude_start"]),
        longitude_start=float(row["longitude_start"]),
        latitude_end=float(row["latitude_end"]),
        longitude_end=float(row["longitude_end"]),
    )


def _event_message(row: dict, millis) -> common_pb2.SafetyEvent:
    return common_pb2.SafetyEvent(
        id=int(row["id"]),
        train_id=row["train_id"] or "",
        block_id=row["block_id"] or "",
        event_type=row["event_type"],
        severity=row["severity"],
        message=row["message"],
        timestamp=millis(row["created_at"]),
    )


def _command_message(row: dict, millis) -> common_pb2.CommandRecord:
    return common_pb2.CommandRecord(
        id=int(row["id"]),
        train_id=row["train_id"] or "",
        command_type=row["command_type"],
        operator_id=row["operator_id"],
        status=row["status"],
        details=row["details"] or "",
        timestamp=millis(row["created_at"]),
        target_id=row["target_id"] or "",
    )


class TelemetryServicer(telemetry_pb2_grpc.TelemetryServiceServicer):
    def __init__(self, db: Database) -> None:
        self.db = db

    def _state(self) -> common_pb2.RailroadStateResponse:
        snapshot = load_railroad_state(self.db)
        millis = snapshot["millis"]
        meta = snapshot["meta"] or {}
        return common_pb2.RailroadStateResponse(
            trains=[_train_message(row) for row in snapshot["trains"]],
            blocks=[_block_message(row) for row in snapshot["blocks"]],
            tick=int(meta.get("tick") or 0),
            timestamp=int(time.time() * 1000),
            events=[_event_message(row, millis) for row in snapshot["events"]],
            commands=[_command_message(row, millis) for row in snapshot["commands"]],
            weather=meta.get("weather") or "DESPEJADO",
            simulation_running=bool(meta.get("running", True)),
        )

    def IngestBatch(self, request, context):
        del context
        stored = ingest_batch(self.db, request.samples)
        return telemetry_pb2.IngestAck(
            success=True,
            stored=stored,
            details=f"{stored} muestras persistidas",
        )

    def RecordSafetyEvent(self, request, context):
        del context
        record_safety_event(self.db, request)
        return telemetry_pb2.IngestAck(success=True, stored=1, details="evento registrado")

    def GetRailroadState(self, request, context):
        del request, context
        return self._state()

    def StreamRailroadState(self, request, context):
        del request
        connection = psycopg.connect(self.db.url, autocommit=True, row_factory=dict_row)
        try:
            connection.execute("LISTEN ptc_state")
            while context.is_active():
                yield self._state()
                for _notice in connection.notifies(timeout=1.0, stop_after=1):
                    break
        finally:
            connection.close()


def main() -> None:
    configure_logging()
    cfg = settings()
    wait_for_db(cfg.database_url)
    db = Database(cfg.database_url, cfg.application_name)
    serve(
        telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server,
        TelemetryServicer(db),
        cfg.port,
        "Telemetry & State Service",
    )


if __name__ == "__main__":
    main()
