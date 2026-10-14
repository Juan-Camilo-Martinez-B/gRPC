from __future__ import annotations

import logging

from railway.ptc.v1 import dispatch_pb2_grpc

from ptc_common.config import settings
from ptc_common.db import Database, wait_for_db
from ptc_common.runtime import configure_logging, serve

from app.logic import DispatchServicer as DispatchLogic

log = logging.getLogger("ptc.dispatch")


class DispatchServicer(dispatch_pb2_grpc.DispatchServiceServicer):
    def __init__(self, logic: DispatchLogic) -> None:
        self.logic = logic

    def SendDispatchCommand(self, request, context):
        del context
        ack = self.logic.handle(request)
        log.info("comando %s success=%s: %s", request.command_type, ack.success, ack.details)
        return ack


def main() -> None:
    configure_logging()
    cfg = settings()
    wait_for_db(cfg.database_url)
    db = Database(cfg.database_url, cfg.application_name)
    logic = DispatchLogic(db, cfg.track_addr, cfg.simulation_addr, cfg.telemetry_addr)
    serve(
        dispatch_pb2_grpc.add_DispatchServiceServicer_to_server,
        DispatchServicer(logic),
        cfg.port,
        "Command & Dispatch Service",
    )


if __name__ == "__main__":
    main()
