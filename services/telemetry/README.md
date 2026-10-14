# Telemetry & State Service

Puerto **50054**. Recibe las muestras del simulador, guarda los eventos de seguridad y proyecta el estado que pinta el OCC.

## RPC

| RPC | Tipo | Uso |
| --- | --- | --- |
| `IngestBatch` | unario | Inserta el lote de `telemetry_logs` de un tick en una sola transacción |
| `RecordSafetyEvent` | unario | Inserta en `safety_events` y notifica al OCC |
| `GetRailroadState` | unario | Foto actual de trenes, bloques, eventos y órdenes |
| `StreamRailroadState` | stream de servidor | La misma foto, emitida al conectar, en cada `NOTIFY ptc_state` y como máximo cada 1 s |

El stream hace `LISTEN ptc_state` en una conexión dedicada. El navegador lo consume a través de Envoy; no hay sondeo REST.

La proyección lee las tablas compartidas. No modifica trenes ni bloques: si una muestra llega, solo se añade el historial de telemetría.
