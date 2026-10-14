from __future__ import annotations

import logging
from datetime import datetime, timezone

from ptc_common.db import Database

log = logging.getLogger("ptc.telemetry")


def _millis(value) -> int:
    if value is None:
        return 0
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(moment.timestamp() * 1000)
    return int(value)


def ingest_batch(db: Database, samples) -> int:
    if not samples:
        return 0
    rows = [
        (
            sample.train_id,
            sample.block_id,
            sample.latitude,
            sample.longitude,
            sample.speed_kmh,
            sample.braking_distance_m,
            sample.distance_to_hazard_m,
            sample.acceleration_mps2,
            sample.signal or "PROCEED",
            int(sample.timestamp or 0),
        )
        for sample in samples
    ]
    with db.transaction() as cur:
        cur.executemany(
            """
            INSERT INTO telemetry_logs (
                train_id, block_id, latitude, longitude, speed_kmh,
                braking_distance_m, distance_to_hazard_m, acceleration_mps2,
                signal, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, to_timestamp(%s / 1000.0)
            )
            """,
            rows,
        )
    log.info("telemetría almacenada: %s muestras", len(rows))
    return len(rows)


def record_safety_event(db: Database, event) -> None:
    with db.transaction() as cur:
        cur.execute(
            """
            INSERT INTO safety_events (
                train_id, block_id, event_type, severity, message, signal_status, created_at
            ) VALUES (
                NULLIF(%s, ''), NULLIF(%s, ''), %s, %s, %s, NULLIF(%s, ''),
                CASE WHEN %s > 0 THEN to_timestamp(%s / 1000.0) ELSE now() END
            )
            """,
            (
                event.train_id,
                event.block_id,
                event.event_type or "SAFETY",
                event.severity or "INFO",
                event.message or "evento de seguridad",
                event.event_type if False else "",
                int(event.timestamp or 0),
                int(event.timestamp or 0),
            ),
        )
        cur.execute("SELECT pg_notify('ptc_state', 'safety')")
    log.info("evento %s %s: %s", event.severity, event.event_type, event.message)


def load_railroad_state(db: Database) -> dict:
    with db.transaction() as cur:
        cur.execute("SELECT * FROM trains ORDER BY train_id")
        trains = list(cur.fetchall())
        cur.execute(
            """
            SELECT *
              FROM railway_blocks
             ORDER BY line_id, sequence_order, block_id
            """
        )
        blocks = list(cur.fetchall())
        cur.execute(
            """
            SELECT *
              FROM safety_events
             ORDER BY id DESC
             LIMIT 40
            """
        )
        events = list(cur.fetchall())
        cur.execute(
            """
            SELECT *
              FROM dispatch_commands
             ORDER BY id DESC
             LIMIT 15
            """
        )
        commands = list(cur.fetchall())
        cur.execute("SELECT * FROM simulation_meta WHERE id = 1")
        meta = cur.fetchone()
    return {
        "trains": trains,
        "blocks": blocks,
        "events": events,
        "commands": commands,
        "meta": meta,
        "millis": _millis,
    }
