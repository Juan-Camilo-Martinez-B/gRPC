# Envoy

Imagen `envoyproxy/envoy:v1.32.3`. Escucha en el puerto **8080** y publica el admin en **9901**.

## Qué hace

1. Acepta gRPC-Web (`application/grpc-web+proto`) desde el navegador, incluido el preflight CORS.
2. El filtro `envoy.filters.http.grpc_web` lo convierte en gRPC.
3. Cada clúster habla **HTTP/2 explícito** con el microservicio (`http2_protocol_options`).
4. El prefijo del path elige el destino: `/railway.ptc.v1.TelemetryService`, `DispatchService`, `SimulationService`, `TrackService` o `BrakingService`.
5. El timeout de ruta es `0s` para no cortar `StreamRailroadState`.

El panel solo necesita Telemetry y Dispatch. El resto de las rutas quedan abiertas para inspección con un cliente gRPC-Web o `grpcurl` contra el puerto interno de cada servicio.
