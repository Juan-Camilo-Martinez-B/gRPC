from __future__ import annotations

import logging
from datetime import datetime, timezone

from ptc_common.db import Database

log = logging.getLogger("ptc.simulation")


def load_world(db: Database) -> tuple[list[dict], dict[str, dict], dict]:
    with db.transaction() as cur:
        cur.execute("SELECT * FROM trains ORDER BY train_id")
        trains = list(cur.fetchall())
        cur.execute("SELECT * FROM railway_blocks")
        blocks = {row["block_id"]: row for row in cur.fetchall()}
        cur.execute("SELECT * FROM simulation_meta WHERE id = 1")
        meta = cur.fetchone()
    return trains, blocks, meta


def force_adhesion(db: Database, train_id: str, adhesion: float, seconds: int) -> int:
    adhesion = min(1.0, max(0.15, adhesion))
    seconds = max(1, int(seconds))
    with db.transaction() as cur:
        if train_id:
            cur.execute(
                "SELECT train_id FROM trains WHERE train_id = %s FOR UPDATE",
                (train_id,),
            )
            if cur.fetchone() is None:
                return 0
            cur.execute(
                """
                UPDATE trains
                   SET adhesion_factor = %s,
                       anomaly_until = now() + make_interval(secs => %s),
                       updated_at = now()
                 WHERE train_id = %s
                """,
                (adhesion, seconds, train_id),
            )
            affected = 1
        else:
            cur.execute("SELECT train_id FROM trains ORDER BY train_id FOR UPDATE")
            affected = len(cur.fetchall())
            cur.execute(
                """
                UPDATE trains
                   SET adhesion_factor = %s,
                       anomaly_until = now() + make_interval(secs => %s),
                       updated_at = now()
                """,
                (adhesion, seconds),
            )
        cur.execute(
            """
            UPDATE simulation_meta
               SET weather = 'LLUVIA / BAJA ADHERENCIA',
                   updated_at = now()
             WHERE id = 1
            """
        )
        cur.execute("SELECT pg_notify('ptc_state', 'weather')")
    log.info("adherencia %.2f durante %ss sobre %s", adhesion, seconds, train_id or "toda la flota")
    return affected


def apply_motion(
    db: Database,
    train_id: str,
    *,
    speed_kmh: float,
    position_m: float,
    latitude: float,
    longitude: float,
    status: str,
    signal: str,
    braking_distance_m: float,
    distance_to_hazard_m: float,
    adhesion_factor: float,
    max_decel_mps2: float,
    dt: float,
) -> dict | None:
    with db.transaction() as cur:
        cur.execute(
            "SELECT * FROM trains WHERE train_id = %s FOR UPDATE",
            (train_id,),
        )
        locked = cur.fetchone()
        if locked is None:
            return None
        cur.execute(
            "SELECT length_m FROM railway_blocks WHERE block_id = %s",
            (locked["current_block_id"],),
        )
        block = cur.fetchone()
        max_position = float(block["length_m"]) - 0.5 if block else position_m
        speed = max(0.0, speed_kmh)
        status_out = status
        signal_out = signal
        if locked["manual_hold"]:
            signal_out = "EMERGENCY_BRAKE"
            status_out = "EMERGENCY"
            forced = max(0.0, float(locked["speed_kmh"]) - max_decel_mps2 * 3.6 * dt)
            speed = min(speed, forced)
        position = min(max(0.0, position_m), max_position)
        adhesion = min(1.0, max(0.15, adhesion_factor))
        now = datetime.now(timezone.utc)
        if locked["anomaly_until"] is not None and locked["anomaly_until"] <= now:
            adhesion = 1.0
        cur.execute(
            """
            UPDATE trains
               SET speed_kmh = %s,
                   position_m = %s,
                   latitude = %s,
                   longitude = %s,
                   status = %s,
                   signal = %s,
                   braking_distance_m = %s,
                   distance_to_hazard_m = %s,
                   adhesion_factor = %s,
                   anomaly_until = CASE WHEN %s THEN NULL ELSE anomaly_until END,
                   updated_at = now()
             WHERE train_id = %s
             RETURNING *
            """,
            (
                speed,
                position,
                latitude,
                longitude,
                status_out,
                signal_out,
                braking_distance_m,
                distance_to_hazard_m,
                adhesion,
                adhesion >= 0.999,
                train_id,
            ),
        )
        return cur.fetchone()


def advance_tick(db: Database) -> int:
    with db.transaction() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM trains WHERE adhesion_factor < 0.95")
        degraded = int(cur.fetchone()["n"])
        weather = "LLUVIA / BAJA ADHERENCIA" if degraded else "DESPEJADO"
        cur.execute(
            """
            UPDATE simulation_meta
               SET tick = tick + 1,
                   running = TRUE,
                   weather = %s,
                   updated_at = now()
             WHERE id = 1
             RETURNING tick
            """,
            (weather,),
        )
        tick = int(cur.fetchone()["tick"])
        cur.execute("SELECT pg_notify('ptc_state', %s)", (str(tick),))
        return tick


def read_status(db: Database) -> tuple[dict, int]:
    with db.transaction() as cur:
        cur.execute("SELECT * FROM simulation_meta WHERE id = 1")
        meta = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS n FROM trains")
        count = int(cur.fetchone()["n"])
    return meta, count
