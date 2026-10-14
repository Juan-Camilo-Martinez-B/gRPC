# Braking Calculation Service

Puerto **50053**. Calcula la curva de frenado y devuelve la señal de protección. No mueve trenes ni ocupa bloques.

## RPC

| RPC | Tipo | Uso |
| --- | --- | --- |
| `StreamTelemetryAndControl` | bidireccional | Lazo automático: entra `TrainTelemetryInput`, sale `ControlCommandOutput` |
| `CalculateBrakingCurve` | unario | La misma decisión, usada si el stream se reconecta a mitad de un tick |

## Modelo

- Adherencia útil × 0.20 da el coeficiente de fricción rueda-carril.
- `grade_percent > 0` es bajada y resta deceleración.
- Un tren más pesado que 200 t reduce la deceleración disponible.
- La distancia de parada es `v·1.8 s + v² / (2a)`, con un piso de 0.35 m/s².
- Se compara esa distancia, multiplicada por 1.35, con la autoridad hasta el próximo bloque ocupado, en alerta, en mantenimiento o hasta el fin de vía.

| Condición | Señal |
| --- | --- |
| Autoridad ≤ 55 % de la distancia exigida | `EMERGENCY_BRAKE` |
| Autoridad ≤ distancia exigida | `STOP` |
| Autoridad ≤ 1.8 × distancia exigida | `CAUTION` (objetivo 45 km/h) |
| Resto | `PROCEED` |

Si la lectura de la vía falla, la respuesta es `EMERGENCY_BRAKE`. El cálculo usa una foto confirmada de `railway_blocks`; la exclusión mutua de la ocupación sigue siendo responsabilidad de Track.
