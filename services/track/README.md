# Track Management Service

Puerto **50052**. Administra el estado físico de la vía. Es el único servicio que cambia `railway_blocks`.

## RPC

| RPC | Tipo | Efecto |
| --- | --- | --- |
| `ListBlocks` | unario | Devuelve la topología y libera retenciones vencidas |
| `OccupyBlock` | unario | Enclavamiento: mueve un tren al bloque siguiente o lo rechaza |
| `SetBlockStatus` | unario | Pone `FREE`, `ALERT` o `MAINTENANCE` en un bloque vacío |
| `SetSwitch` | unario | Mueve la aguja de `M05` a `NORMAL` o `REVERSE` |

## Reglas de ocupación

La transacción bloquea las filas implicadas con `SELECT … FOR UPDATE` antes de escribir. Niega la entrada cuando:

- el destino no es sucesor legal del bloque actual, teniendo en cuenta la aguja;
- el destino está `OCCUPIED` por otro tren, en `ALERT` o en `MAINTENANCE`;
- no se obtiene el bloqueo dentro de 2 s.

`SetSwitch` también toma la fila de la aguja. Si hay un tren sobre ese bloque, la aguja queda enclavada y la orden se rechaza.

Un hilo interno barre cada 2 s las retenciones cuyo `hold_until` ya venció, con `FOR UPDATE SKIP LOCKED`.
