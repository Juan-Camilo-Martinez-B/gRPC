from __future__ import annotations

import asyncio
import logging

from railway.ptc.v1 import common_pb2, simulation_pb2, simulation_pb2_grpc

import grpc
from concurrent.futures import ThreadPoolExecutor

from ptc_common.config import settings
from ptc_common.db import Database, wait_for_db
from ptc_common.runtime import configure_logging

from app.engine import SimulationEngine
from app.repository import force_adhesion, read_status

log = logging.getLogger("ptc.simulation")


class SimulationServicer(simulation_pb2_grpc.SimulationServiceServicer):
    def __init__(self, db: Database) -> None:
        self.db = db

    def InjectAnomaly(self, request, context):
        del context
        kind = request.kind.strip().upper() or "WEATHER_ADHESION"
        if kind != "WEATHER_ADHESION":
            return common_pb2.CommandAcknowledgment(
                success=False,
                details=f"Anomalía no soportada: {kind}",
            )
        adhesion = request.adhesion_factor if 0 < request.adhesion_factor <= 1 else 0.30
        seconds = request.duration_seconds if request.duration_seconds > 0 else 30
        affected = force_adhesion(self.db, request.train_id.strip(), adhesion, seconds)
        if affected == 0:
            return common_pb2.CommandAcknowledgment(
                success=False,
                details=f"No se encontró el tren {request.train_id}",
            )
        scope = request.train_id.strip() or "toda la flota"
        return common_pb2.CommandAcknowledgment(
            success=True,
            details=(
                f"Adherencia {adhesion:.2f} durante {seconds}s sobre {scope}. "
                "El frenado predictivo recalculará la curva en el siguiente tick."
            ),
        )

    def GetSimulationStatus(self, request, context):
        del request, context
        meta, count = read_status(self.db)
        return simulation_pb2.SimulationStatus(
            tick=int(meta["tick"]) if meta else 0,
            running=bool(meta["running"]) if meta else False,
            weather=meta["weather"] if meta else "DESPEJADO",
            train_count=count,
        )


def main() -> None:
    configure_logging()
    cfg = settings()
    wait_for_db(cfg.database_url)
    db = Database(cfg.database_url, cfg.application_name)
    grpc_server = grpc.server(ThreadPoolExecutor(max_workers=8))
    simulation_pb2_grpc.add_SimulationServiceServicer_to_server(SimulationServicer(db), grpc_server)
    grpc_server.add_insecure_port(f"0.0.0.0:{cfg.port}")
    grpc_server.start()
    log.info("Simulation Engine Service escuchando gRPC/HTTP2 en el puerto %s", cfg.port)
    engine = SimulationEngine(cfg, db)
    try:
        asyncio.run(engine.run())
    finally:
        grpc_server.stop(3)
        db.close()


if __name__ == "__main__":
    main()
