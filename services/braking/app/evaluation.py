from __future__ import annotations

import logging

from ptc_common.db import Database
from ptc_common.topology import successors

from app.physics import SAFETY_FACTOR, stopping_distance

log = logging.getLogger("ptc.braking")


def load_blocks(db: Database) -> dict[str, dict]:
    with db.transaction() as cur:
        cur.execute("SELECT * FROM railway_blocks")
        return {row["block_id"]: row for row in cur.fetchall()}


def _distance_to_hazard(
    train_id: str,
    block_id: str,
    position_m: float,
    blocks: dict[str, dict],
) -> tuple[float, str]:
    current = blocks.get(block_id)
    if current is None:
        return 0.0, block_id or "UNKNOWN"
    if current["status"] in {"ALERT", "MAINTENANCE"}:
        return 0.0, block_id

    switch = "NORMAL"
    switch_row = blocks.get("M05")
    if switch_row is not None:
        switch = switch_row["switch_position"]

    remaining = max(0.0, float(current["length_m"]) - position_m)
    traveled = remaining
    cursor = successors(block_id, switch)
    visited = {block_id}
    last_id = block_id
    for _ in range(24):
        if not cursor:
            return traveled, "END_OF_AUTHORITY"
        next_id = cursor[0]
        if next_id in visited:
            return traveled, next_id
        visited.add(next_id)
        nxt = blocks.get(next_id)
        if nxt is None:
            return traveled, next_id
        occupier = nxt["occupied_by_train_id"]
        blocked = nxt["status"] in {"OCCUPIED", "ALERT", "MAINTENANCE"} and occupier != train_id
        if blocked:
            return traveled, next_id
        traveled += float(nxt["length_m"])
        last_id = next_id
        cursor = successors(next_id, switch)
    return traveled, last_id


def evaluate(telemetry, blocks: dict[str, dict]) -> dict:
    adhesion = telemetry.adhesion_factor if telemetry.adhesion_factor > 0 else 0.2
    mass = telemetry.mass_kg if telemetry.mass_kg > 0 else 200_000.0
    speed = max(0.0, telemetry.speed_kmh)
    cruise = telemetry.cruise_speed_kmh if telemetry.cruise_speed_kmh > 0 else speed
    block = blocks.get(telemetry.current_block_id)
    grade = float(block["grade_percent"]) if block else 0.0
    braking = stopping_distance(speed, adhesion, grade, mass)
    distance, hazard = _distance_to_hazard(
        telemetry.train_id,
        telemetry.current_block_id,
        telemetry.position_m,
        blocks,
    )
    required = braking * SAFETY_FACTOR
    end_of_line = hazard == "END_OF_AUTHORITY" and distance < max(120.0, required)

    if end_of_line and (distance < 40.0 or speed > 30.0):
        signal = "EMERGENCY_BRAKE" if speed > 25.0 and distance < 40.0 else "STOP"
        target = 0.0
        severity = "fin de la autoridad de movimiento"
    elif distance <= required * 0.55:
        signal = "EMERGENCY_BRAKE"
        target = 0.0
        severity = "distancia menor que el 55 % de la curva de frenado"
    elif distance <= required:
        signal = "STOP"
        target = 0.0
        severity = "la autoridad de movimiento no cubre la distancia de parada"
    elif distance <= required * 1.8:
        signal = "CAUTION"
        target = min(cruise, 45.0)
        severity = "aproximación a la curva de frenado"
    else:
        signal = "PROCEED"
        target = cruise
        severity = "margen de seguridad suficiente"

    message = (
        f"{telemetry.train_id}: {signal}. "
        f"v={speed:.1f} km/h, parada={braking:.0f} m, "
        f"autoridad={distance:.0f} m, peligro={hazard}, "
        f"adherencia={adhesion:.2f}, pendiente={grade:.2f} %. {severity}."
    )
    if signal != "PROCEED":
        log.info(message)
    return {
        "signal": signal,
        "message": message,
        "braking_distance_m": braking,
        "distance_to_hazard_m": distance,
        "target_speed_kmh": target,
        "hazard_block_id": hazard,
    }
