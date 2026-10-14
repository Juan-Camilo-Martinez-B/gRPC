from __future__ import annotations

import logging
import threading
import time

import grpc
from railway.ptc.v1 import common_pb2, track_pb2, track_pb2_grpc

from ptc_common.config import settings
from ptc_common.db import Database, wait_for_db
from ptc_common.runtime import configure_logging, serve

from app.repository import list_blocks, occupy_block, set_block_status, set_switch, sweep_expired_holds

log = logging.getLogger("ptc.track")


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


class TrackServicer(track_pb2_grpc.TrackServiceServicer):
    def __init__(self, db: Database) -> None:
        self.db = db

    def ListBlocks(self, request, context):
        del request, context
        rows = list_blocks(self.db)
        return track_pb2.BlockList(blocks=[_block_message(row) for row in rows])

    def OccupyBlock(self, request, context):
        granted, details = occupy_block(
            self.db,
            request.train_id.strip(),
            request.block_id.strip(),
            float(request.entry_position_m),
            float(request.speed_kmh),
        )
        if not granted:
            context.set_code(grpc.StatusCode.OK)
        return track_pb2.OccupyBlockResponse(granted=granted, details=details)

    def SetBlockStatus(self, request, context):
        del context
        ok, details = set_block_status(
            self.db,
            request.block_id.strip(),
            request.status.strip().upper(),
            int(request.hold_seconds),
            request.reason.strip(),
        )
        return common_pb2.CommandAcknowledgment(success=ok, details=details)

    def SetSwitch(self, request, context):
        del context
        ok, details = set_switch(
            self.db,
            request.block_id.strip() or "M05",
            request.position.strip().upper(),
            request.operator_id.strip(),
        )
        return common_pb2.CommandAcknowledgment(success=ok, details=details)


def _sweeper(db: Database) -> None:
    while True:
        try:
            sweep_expired_holds(db)
        except Exception:  # noqa: BLE001 - el hilo no debe morir
            log.exception("falló el barrido de retenciones de vía")
        time.sleep(2)


def main() -> None:
    configure_logging()
    cfg = settings()
    wait_for_db(cfg.database_url)
    db = Database(cfg.database_url, cfg.application_name)
    threading.Thread(target=_sweeper, args=(db,), name="track-sweep", daemon=True).start()
    serve(
        track_pb2_grpc.add_TrackServiceServicer_to_server,
        TrackServicer(db),
        cfg.port,
        "Track Management Service",
    )


if __name__ == "__main__":
    main()
