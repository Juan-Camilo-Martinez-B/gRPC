# Plataforma de Telemetría y Control de Tráfico Ferroviario (PTC)

Sistema de señalización para un corredor de alta velocidad. Cinco microservicios se hablan entre sí **solo con gRPC sobre HTTP/2** y Protocol Buffers. El panel del centro de control (OCC) consume el mismo contrato mediante **gRPC-Web**, traducido por Envoy. Todos los servicios leen y escriben una **única base PostgreSQL**.

## Cómo levantarlo

Requisito: Docker Desktop (o Docker Engine con Compose v2).

```bash
docker compose up --build
```

Cuando los contenedores estén sanos:

- Panel OCC: http://localhost:3000
- Pasarela gRPC-Web: http://localhost:8080
- PostgreSQL: `localhost:5432` (usuario `ptc`, contraseña `ptc_railway`, base `ptc`)

Para borrar el estado de la vía y volver a cargar el esquema:

```bash
docker compose down -v
docker compose up --build
```

## Qué se ve en el OCC

El expreso `EXP-01` circula detrás del regional `REG-14`. En los primeros ticks el motor de frenado publica precaución o parada porque la distancia de parada no cabe en la autoridad de movimiento. Además:

- **Frenado de emergencia** retiene uno o todos los trenes (`manual_hold`) hasta que el operador los libera.
- **Anomalía climática** baja la adherencia a 0.30 durante 30 s y obliga a recalcular la curva.
- **Aguja M05** conmuta entre la vía normal (M06) y el apartadero (S01–S03). Si hay un tren sobre M05, el enclavamiento rechaza el movimiento.
- Cada ~12–25 s el simulador puede marcar un bloque libre por delante como `ALERT`.

## Mapa de red

```text
Navegador (OCC, :3000)
        │  gRPC-Web
        ▼
Envoy (:8080) ──HTTP/2 gRPC──► telemetry   :50054
                     ├────────► dispatch    :50055
                     ├────────► simulation  :50051
                     ├────────► track       :50052
                     └────────► braking     :50053
                                      │
                                      ▼
                              PostgreSQL :5432
```

En claro (`h2c`) el navegador usa gRPC-Web, normalmente sobre HTTP/1.1, porque HTTP/2 de navegador exige TLS. Envoy abre hacia cada microservicio una conexión **HTTP/2** y multiplexa los RPC. La malla interna no usa REST.

## Contrato del caso de estudio

| Operación del caso | Servicio que la implementa | RPC |
| --- | --- | --- |
| `StreamTelemetryAndControl` | Braking Calculation | `BrakingService.StreamTelemetryAndControl` |
| `GetRailroadState` | Telemetry & State | `TelemetryService.GetRailroadState` y el push `StreamRailroadState` |
| `SendDispatchCommand` | Command & Dispatch | `DispatchService.SendDispatchCommand` |

Los campos originales de telemetría, señal, estado de vía y acuse conservan su número de campo. El OCC usa el stream de servidor `StreamRailroadState` para recibir el tablero sin polling.

## Integridad de la base compartida

La vía es un recurso físico único, así que la ocupación no se reparte en bases distintas. El orden de bloqueo es siempre:

1. `railway_blocks` por `block_id` ascendente (`SELECT … FOR UPDATE`)
2. `trains` por `train_id` ascendente

Eso evita interbloqueos entre el enclavamiento, el simulador y el despacho. Un bloque en `MAINTENANCE` no puede recibir un tren: lo impide el servicio de vía y un trigger de PostgreSQL. El detalle está en `db/README.md`.

## Módulos

| Carpeta | Rol |
| --- | --- |
| `proto/` | Contratos `.proto` |
| `db/` | Esquema y datos iniciales |
| `shared/` | Pool SQL, topología y arranque gRPC |
| `services/simulation` | Ticks, movimiento y eventos estocásticos |
| `services/track` | Enclavamiento y agujas |
| `services/braking` | Curvas de frenado y stream bidireccional |
| `services/telemetry` | Ingesta y proyección de estado |
| `services/dispatch` | Órdenes del OCC |
| `envoy/` | Pasarela gRPC-Web |
| `frontend/` | Panel OCC |
