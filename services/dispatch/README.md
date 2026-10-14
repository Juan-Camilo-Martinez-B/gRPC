# Command & Dispatch Service

Puerto **50055**. Única entrada de las acciones del operador. Traduce `SendDispatchCommand` en una escritura transaccional o en un RPC interno.

## RPC

| RPC | Tipo | Uso |
| --- | --- | --- |
| `SendDispatchCommand` | unario | Ejecuta la orden y devuelve `CommandAcknowledgment` |

## Comandos

| `command_type` | Efecto |
| --- | --- |
| `EMERGENCY_STOP` | `manual_hold` y señal `EMERGENCY_BRAKE` en el tren o en toda la flota (`train_id = "*"`), con `FOR UPDATE` |
| `RELEASE_TRAIN` | Quita la retención manual |
| `SWITCH_NORMAL` / `SWITCH_REVERSE` | Llama a `TrackService.SetSwitch` |
| `SIMULATE_WEATHER` | Llama a `SimulationService.InjectAnomaly` |

Toda orden, aplicada o rechazada, queda en `dispatch_commands`. Las de emergencia y liberación también generan un `safety_events` a través de Telemetry. Después del commit se emite `NOTIFY ptc_state` para que el panel no espere al siguiente tick.
