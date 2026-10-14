from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    port: int
    track_addr: str
    braking_addr: str
    telemetry_addr: str
    dispatch_addr: str
    simulation_addr: str
    tick_seconds: float
    application_name: str


def settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://ptc:ptc_railway@localhost:5432/ptc",
        ),
        port=int(os.environ.get("PORT", "50051")),
        track_addr=os.environ.get("TRACK_ADDR", "localhost:50052"),
        braking_addr=os.environ.get("BRAKING_ADDR", "localhost:50053"),
        telemetry_addr=os.environ.get("TELEMETRY_ADDR", "localhost:50054"),
        dispatch_addr=os.environ.get("DISPATCH_ADDR", "localhost:50055"),
        simulation_addr=os.environ.get("SIMULATION_ADDR", "localhost:50051"),
        tick_seconds=float(os.environ.get("TICK_SECONDS", "1.0")),
        application_name=os.environ.get("APPLICATION_NAME", "ptc"),
    )
