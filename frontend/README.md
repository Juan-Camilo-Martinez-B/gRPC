# Panel OCC

React y TypeScript, servidos por nginx en el puerto **3000**. El navegador no usa REST: `src/grpc/client.ts` habla gRPC-Web con Envoy en `http://localhost:8080` (o `VITE_GRPC_WEB_URL`).

## Qué muestra

- Corredor M01–M10 y apartadero S01–S03. Verde libre, azul ocupado, ámbar precaución, rojo intermitente alerta o frenado de emergencia, gris mantenimiento.
- Ficha de cada tren con velocidad, bloque, señal, curva de frenado, autoridad de movimiento, adherencia y coordenadas.
- Botones de emergencia, liberación, anomalía climática y aguja.
- Terminal con `safety_events` y `dispatch_commands`.

## Tiempo real

`TelemetryService.StreamRailroadState` permanece abierto. Si Envoy o el servicio cierran el stream, el panel reintenta con espera creciente. Las órdenes son unarios `DispatchService.SendDispatchCommand` multiplexados por el navegador hacia el mismo origen de Envoy.

## Desarrollo sin reconstruir la imagen

Con el backend ya levantado:

```bash
cd frontend
npm install
npm run dev
```

Vite queda en http://localhost:5173 y sigue llamando a Envoy en el puerto 8080.
