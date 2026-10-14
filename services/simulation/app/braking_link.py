from __future__ import annotations

import asyncio
import logging

import grpc

log = logging.getLogger("ptc.simulation.bidi")


class BrakingLink:
    """Cliente del RPC bidireccional StreamTelemetryAndControl.

    Mantiene un stream abierto: cada telemetría sale por la cola de escritura
    y la señal de protección vuelve por la cola de lectura, emparejadas por
    `sequence`. Si el stream cae, se reabre y el tick se completa con el RPC
    unario CalculateBrakingCurve.
    """

    def __init__(self, address: str) -> None:
        self.address = address
        self.channel: grpc.aio.Channel | None = None
        self.unary = None
        self._out: asyncio.Queue = asyncio.Queue()
        self._in: asyncio.Queue = asyncio.Queue()
        self._reader: asyncio.Task | None = None

    async def connect(self) -> None:
        previous_out = self._out
        previous_reader = self._reader
        if previous_reader is not None:
            await previous_out.put(None)
            previous_reader.cancel()
            try:
                await asyncio.wait_for(previous_reader, timeout=1)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if self.channel is not None:
            await self.channel.close()

        out_queue: asyncio.Queue = asyncio.Queue()
        in_queue: asyncio.Queue = asyncio.Queue()
        self._out = out_queue
        self._in = in_queue
        self.channel = grpc.aio.insecure_channel(self.address)
        await self.channel.channel_ready()

        from railway.ptc.v1 import braking_pb2_grpc

        stub = braking_pb2_grpc.BrakingServiceStub(self.channel)
        self.unary = stub.CalculateBrakingCurve

        async def outgoing():
            while True:
                item = await out_queue.get()
                if item is None:
                    return
                yield item

        call = stub.StreamTelemetryAndControl(outgoing())

        async def incoming() -> None:
            try:
                async for response in call:
                    await in_queue.put(response)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - se reporta al intercambio
                await in_queue.put(exc)
            finally:
                await in_queue.put(None)

        self._reader = asyncio.create_task(incoming(), name="braking-bidi")
        log.info("stream bidireccional de frenado establecido con %s", self.address)

    async def exchange(self, message, timeout: float = 3.0):
        if self.unary is None or self._reader is None:
            await self.connect()
        try:
            await self._out.put(message)
            item = await asyncio.wait_for(self._in.get(), timeout)
            if item is None or isinstance(item, Exception):
                raise RuntimeError(f"stream de frenado cerrado: {item}")
            if item.sequence != message.sequence:
                raise RuntimeError(
                    f"secuencia de frenado {item.sequence} distinta de {message.sequence}"
                )
            return item
        except Exception:
            log.warning(
                "el stream bidireccional falló para %s; se usa CalculateBrakingCurve",
                message.train_id,
                exc_info=True,
            )
            await self.connect()
            return await self.unary(message, timeout=timeout)
