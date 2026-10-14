"""Crea el esquema PTC en Supabase si todavía no existe."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg


def main() -> None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL es obligatorio", file=sys.stderr)
        sys.exit(1)
    schema = Path("/app/db/init.sql")
    with psycopg.connect(url, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.trains')")
            exists = cur.fetchone()[0]
    if exists:
        print("Esquema PTC ya presente; no se vuelve a cargar init.sql")
        return
    print("Cargando esquema PTC en la base compartida")
    subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", "-f", str(schema)],
        check=True,
    )


if __name__ == "__main__":
    main()
