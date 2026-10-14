from __future__ import annotations

import logging

import psycopg
from psycopg import errors

from ptc_common.db import Database
from ptc_common.topology import SWITCH_BLOCK, interpolate, successors

log = logging.getLogger("ptc.track")


def sweep_expired_holds(db: Database) -> int:
    with db.transaction() as cur:
        cur.execute(
            """
            SELECT block_id
              FROM railway_blocks
             WHERE status IN ('ALERT', 'MAINTENANCE')
               AND hold_until IS NOT NULL
               AND hold_until < now()
               AND occupied_by_train_id IS NULL
             ORDER BY block_id
               FOR UPDATE SKIP LOCKED
            """
        )
        block_ids = [row["block_id"] for row in cur.fetchall()]
        if not block_ids:
            return 0
        cur.execute(
            """
            UPDATE railway_blocks
               SET status = 'FREE',
                   hold_until = NULL,
                   signal_aspect = 'PROCEED',
                   updated_at = now()
             WHERE block_id = ANY(%s)
            """,
            (block_ids,),
        )
        cur.execute("SELECT pg_notify('ptc_state', 'sweep')")
        log.info("Bloques liberados por vencimiento de retención: %s", ", ".join(block_ids))
        return len(block_ids)


def list_blocks(db: Database) -> list[dict]:
    sweep_expired_holds(db)
    with db.transaction() as cur:
        cur.execute(
            """
            SELECT *
              FROM railway_blocks
             ORDER BY line_id, sequence_order, block_id
            """
        )
        return list(cur.fetchall())


def _fail(message: str) -> tuple[bool, str]:
    log.info("movimiento rechazado: %s", message)
    return False, message


def occupy_block(
    db: Database,
    train_id: str,
    block_id: str,
    entry_position_m: float,
    speed_kmh: float,
) -> tuple[bool, str]:
    """Enclavamiento pesimista.

    Bloquea las filas de vía en orden de block_id y después el tren.
    Dos ocupaciones concurrentes del mismo bloque se serializan: la segunda
    observa el bloque ya OCCUPIED y se rechaza.
    """
    try:
        with db.transaction() as cur:
            cur.execute(
                "SELECT current_block_id FROM trains WHERE train_id = %s",
                (train_id,),
            )
            peeked = cur.fetchone()
            if peeked is None:
                return _fail(f"El tren {train_id} no existe")
            current_id = peeked["current_block_id"]
            lock_ids = sorted({block_id, current_id, SWITCH_BLOCK} - {None})
            cur.execute(
                """
                SELECT *
                  FROM railway_blocks
                 WHERE block_id = ANY(%s)
                 ORDER BY block_id
                   FOR UPDATE
                """,
                (lock_ids,),
            )
            locked_blocks = {row["block_id"]: row for row in cur.fetchall()}
            cur.execute(
                "SELECT * FROM trains WHERE train_id = %s FOR UPDATE",
                (train_id,),
            )
            train = cur.fetchone()
            if train is None:
                return _fail(f"El tren {train_id} no existe")
            if train["current_block_id"] != current_id:
                return _fail("El tren cambió de bloque durante el enclavamiento; reintente")

            current_id = train["current_block_id"]
            target = locked_blocks.get(block_id)
            if target is None:
                return _fail(f"El bloque {block_id} no existe")
            if current_id == block_id:
                return _fail(f"{train_id} ya ocupa {block_id}")

            switch_row = locked_blocks.get(SWITCH_BLOCK)
            switch_position = switch_row["switch_position"] if switch_row else "NORMAL"
            if current_id is None:
                return _fail("El tren no tiene bloque actual")
            allowed = successors(current_id, switch_position)
            if block_id not in allowed:
                return _fail(
                    f"{block_id} no es sucesor legal de {current_id} con aguja {switch_position}"
                )
            if target["status"] == "MAINTENANCE":
                return _fail(f"{block_id} está inhabilitado por mantenimiento")
            if target["status"] == "ALERT":
                return _fail(f"{block_id} está en alerta; entrada denegada")
            occupier = target["occupied_by_train_id"]
            if target["status"] == "OCCUPIED" and occupier not in (None, train_id):
                return _fail(f"{block_id} ya está ocupado por {occupier}")
            length = float(target["length_m"])
            if entry_position_m < 0 or entry_position_m >= length:
                return _fail("La posición de entrada queda fuera del bloque")
            if speed_kmh < 0:
                return _fail("Velocidad negativa")

            cur.execute(
                """
                UPDATE railway_blocks
                   SET status = 'FREE',
                       occupied_by_train_id = NULL,
                       signal_aspect = 'PROCEED',
                       updated_at = now()
                 WHERE block_id = %s
                   AND occupied_by_train_id = %s
                """,
                (current_id, train_id),
            )
            cur.execute(
                """
                UPDATE railway_blocks
                   SET status = 'OCCUPIED',
                       occupied_by_train_id = %s,
                       signal_aspect = 'PROCEED',
                       updated_at = now()
                 WHERE block_id = %s
                """,
                (train_id, block_id),
            )
            latitude, longitude = interpolate(target, entry_position_m)
            cur.execute(
                """
                UPDATE trains
                   SET current_block_id = %s,
                       position_m = %s,
                       speed_kmh = %s,
                       latitude = %s,
                       longitude = %s,
                       updated_at = now()
                 WHERE train_id = %s
                """,
                (block_id, entry_position_m, speed_kmh, latitude, longitude, train_id),
            )
            cur.execute("SELECT pg_notify('ptc_state', 'occupy')")
            log.info(
                "enclavamiento concedido %s: %s -> %s a %.0f m",
                train_id,
                current_id,
                block_id,
                entry_position_m,
            )
            return True, f"{train_id} entró a {block_id}"
    except errors.LockNotAvailable:
        return _fail("No se obtuvo SELECT FOR UPDATE antes del tiempo límite")
    except errors.QueryCanceled:
        return _fail("La transacción de ocupación excedió el tiempo límite")
    except psycopg.Error as exc:
        log.exception("fallo SQL al ocupar bloque")
        return _fail(f"Integridad rechazó la ocupación: {exc}")


def set_block_status(
    db: Database,
    block_id: str,
    status: str,
    hold_seconds: int,
    reason: str,
) -> tuple[bool, str]:
    if status not in {"FREE", "ALERT", "MAINTENANCE"}:
        return False, "Solo se admiten FREE, ALERT o MAINTENANCE"
    try:
        with db.transaction() as cur:
            cur.execute(
                """
                SELECT *
                  FROM railway_blocks
                 WHERE block_id = %s
                   FOR UPDATE
                """,
                (block_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False, f"El bloque {block_id} no existe"
            if row["occupied_by_train_id"]:
                return False, f"{block_id} está ocupado por {row['occupied_by_train_id']}"
            if status == "FREE":
                cur.execute(
                    """
                    UPDATE railway_blocks
                       SET status = 'FREE',
                           hold_until = NULL,
                           signal_aspect = 'PROCEED',
                           updated_at = now()
                     WHERE block_id = %s
                    """,
                    (block_id,),
                )
            else:
                seconds = max(1, int(hold_seconds or 15))
                aspect = "STOP"
                cur.execute(
                    """
                    UPDATE railway_blocks
                       SET status = %s,
                           signal_aspect = %s,
                           hold_until = now() + make_interval(secs => %s),
                           updated_at = now()
                     WHERE block_id = %s
                    """,
                    (status, aspect, seconds, block_id),
                )
            cur.execute("SELECT pg_notify('ptc_state', 'block-status')")
            detail = reason or f"{block_id} -> {status}"
            log.info("estado de vía %s", detail)
            return True, detail
    except (errors.LockNotAvailable, errors.QueryCanceled):
        return False, "Contención al actualizar el bloque"
    except psycopg.Error as exc:
        return False, f"No se pudo actualizar el bloque: {exc}"


def set_switch(
    db: Database,
    block_id: str,
    position: str,
    operator_id: str,
) -> tuple[bool, str]:
    if position not in {"NORMAL", "REVERSE"}:
        return False, "La aguja solo admite NORMAL o REVERSE"
    try:
        with db.transaction() as cur:
            cur.execute(
                """
                SELECT *
                  FROM railway_blocks
                 WHERE block_id = %s
                   FOR UPDATE
                """,
                (block_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False, f"El bloque {block_id} no existe"
            if row["switch_position"] == "NONE":
                return False, f"{block_id} no tiene aguja"
            if row["occupied_by_train_id"]:
                return False, "Aguja enclavada: hay un tren sobre el bloque"
            cur.execute(
                """
                UPDATE railway_blocks
                   SET switch_position = %s,
                       updated_at = now()
                 WHERE block_id = %s
                """,
                (position, block_id),
            )
            cur.execute("SELECT pg_notify('ptc_state', 'switch')")
            detail = f"Aguja {block_id} en {position} por {operator_id or 'OCC'}"
            log.info(detail)
            return True, detail
    except (errors.LockNotAvailable, errors.QueryCanceled):
        return False, "Contención al mover la aguja"
    except psycopg.Error as exc:
        return False, f"No se pudo mover la aguja: {exc}"
