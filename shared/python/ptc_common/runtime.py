from __future__ import annotations

import logging
from concurrent import futures

import grpc

log = logging.getLogger("ptc.runtime")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def serve(add_servicer, servicer, port: int, service_name: str) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    add_servicer(servicer, server)
    bound = server.add_insecure_port(f"0.0.0.0:{port}")
    if bound == 0:
        raise RuntimeError(f"No se pudo abrir el puerto {port} para {service_name}")
    server.start()
    log.info("%s escuchando gRPC/HTTP2 en el puerto %s", service_name, port)
    server.wait_for_termination()
