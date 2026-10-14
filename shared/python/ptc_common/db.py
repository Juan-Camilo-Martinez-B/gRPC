from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger("ptc.db")


def wait_for_db(url: str, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            log.info("PostgreSQL disponible")
            return
        except Exception as exc:  # noqa: BLE001 - reintento de arranque
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"PostgreSQL no respondió a tiempo: {last_error}")


class Database:
    """Pool corto. Cada transacción toma una conexión y hace commit o rollback."""

    def __init__(self, url: str, application_name: str) -> None:
        self.url = url
        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=8,
            kwargs={
                "row_factory": dict_row,
                "application_name": application_name,
            },
            open=True,
        )

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Cursor]:
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL lock_timeout = '2s'")
                    cur.execute("SET LOCAL statement_timeout = '5s'")
                    yield cur

    def close(self) -> None:
        self.pool.close()
