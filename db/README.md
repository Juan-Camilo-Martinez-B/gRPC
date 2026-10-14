# Base de datos compartida

PostgreSQL 16. El script `init.sql` se ejecuta solo cuando el volumen `ptc-data` está vacío.

## Tablas

| Tabla | Dueño de las escrituras | Contenido |
| --- | --- | --- |
| `railway_blocks` | Track Management | Geometría, pendiente, ocupación, aguja y retenciones |
| `trains` | Simulation (cinemática), Track (bloque actual), Dispatch (retención manual) | Estado dinámico de cada tren |
| `telemetry_logs` | Telemetry | Muestras insertadas en lote por tick |
| `dispatch_commands` | Dispatch | Acuse `APPLIED` o `REJECTED` |
| `safety_events` | Telemetry | Cambios de señal y órdenes críticas |
| `simulation_meta` | Simulation | Tick, clima y bandera de marcha |

## Concurrencia

Cada transacción fija `lock_timeout = 2s` y `statement_timeout = 5s`.

- Ocupar un bloque bloquea el bloque origen, el destino y `M05` (la aguja), en orden de `block_id`, y después la fila del tren.
- Dos trenes no pueden ganar el mismo bloque: el segundo ve `OCCUPIED` y el RPC responde `granted = false`.
- La emergencia bloquea los trenes afectados con `FOR UPDATE` antes de poner `manual_hold`.
- Las retenciones `ALERT` y `MAINTENANCE` vencen con `FOR UPDATE SKIP LOCKED`, así el barrido no espera a una ocupación en curso.

## Reglas que no viven solo en la aplicación

- `trains.current_block_id` referencia un bloque existente.
- `railway_blocks.occupied_by_train_id` referencia un tren, de forma diferida para permitir el intercambio dentro de la transacción.
- El trigger `trains_reject_disabled_block` rechaza asociar un tren a un bloque en `MAINTENANCE`.
- `grade_percent > 0` es pendiente descendente en el sentido de la marcha y alarga la distancia de frenado.

## Datos iniciales

Corredor de 10 bloques de 800 m (`M01`–`M10`) y apartadero `S01`–`S03`. Trenes `EXP-01`, `REG-14` y `FRG-09`, con el expreso acercándose al regional.
