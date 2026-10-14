# Simulation Engine Service

Puerto **50051**. Es el único proceso que mueve trenes. Cada `TICK_SECONDS` (1 s por defecto) recorre la flota de la cabeza hacia la cola, pide una señal de frenado y persiste la nueva cinemática.

## RPC

| RPC | Tipo | Uso |
| --- | --- | --- |
| `InjectAnomaly` | unario | Baja la adherencia de un tren o de toda la flota y marca el clima como lluvia |
| `GetSimulationStatus` | unario | Tick, clima y cantidad de trenes |

No recibe la telemetría del OCC. El lazo de protección sale de este servicio hacia Braking.

## Lazo de un tick

1. Con probabilidad baja, pide a Track que marque `ALERT` un bloque libre por delante, o reduce la adherencia de un tren.
2. Para cada tren, de mayor progresiva a menor, arma un `TrainTelemetryInput` y lo envía por `BrakingService.StreamTelemetryAndControl`.
3. Si ese stream se corta, reabre la sesión y completa el tick con `CalculateBrakingCurve`.
4. Integra velocidad y posición. Si el tren cruza el límite del bloque, llama a `TrackService.OccupyBlock`.
5. Si el enclavamiento niega la entrada, el tren queda detenido al final del bloque actual.
6. Escribe cinemática, distancia de frenado y autoridad con `SELECT … FOR UPDATE` sobre la fila del tren.
7. Pide a Telemetry que guarde el lote y el evento de seguridad si la señal cambió.
8. Incrementa `simulation_meta.tick` y emite `NOTIFY ptc_state`.

`manual_hold` impuesto por Dispatch gana a una señal más permisiva: el tren sigue frenando hasta que el OCC lo libera.

Las coordenadas del tick salen de la interpolación geodésica entre los extremos del bloque, en `shared`.
