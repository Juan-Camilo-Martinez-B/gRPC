# Librería compartida

Código Python importado por los cinco servicios (`ptc_common`). No expone RPC: solo evita que cada servicio reimplemente la conexión, el orden de la vía y el arranque del servidor.

| Módulo | Responsabilidad |
| --- | --- |
| `config.py` | `DATABASE_URL`, puertos y direcciones gRPC |
| `db.py` | Pool `psycopg`, transacciones cortas y espera a PostgreSQL |
| `topology.py` | Sucesores legales de cada bloque, progresiva y coordenadas |
| `runtime.py` | Logging y servidor gRPC en `0.0.0.0` |

`successors()` es la única definición de “bloque siguiente”. La usan el enclavamiento, el simulador y el cálculo de autoridad de movimiento. La aguja `M05` en `NORMAL` entrega `M06`; en `REVERSE`, entrega `S01`. `S03` siempre reingresa a `M07`.
