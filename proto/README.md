# Contratos gRPC

Paquete `railway.ptc.v1`. Los stubs Python se generan en la imagen de cada servicio con `grpc_tools.protoc`; el navegador codifica estos mismos mensajes en el cliente gRPC-Web.

| Archivo | Contenido |
| --- | --- |
| `common.proto` | Telemetría, señales, estado de la red, órdenes y acuses |
| `braking.proto` | `CalculateBrakingCurve` y `StreamTelemetryAndControl` |
| `telemetry.proto` | Ingesta, eventos de seguridad, consulta y stream del OCC |
| `dispatch.proto` | `SendDispatchCommand` |
| `track.proto` | Listado, ocupación, estado de bloque y aguja |
| `simulation.proto` | Inyección de anomalía y estado del reloj de simulación |

## Señales

`PROCEED = 0`, `CAUTION = 1`, `STOP = 2`, `EMERGENCY_BRAKE = 3`.

## Órdenes del OCC

`EMERGENCY_STOP`, `RELEASE_TRAIN`, `SWITCH_NORMAL`, `SWITCH_REVERSE`, `SIMULATE_WEATHER`.

`train_id = "*"` aplica la orden a toda la flota. `target_id` indica el bloque de la aguja. `parameter` es el factor de adherencia de la anomalía climática.
