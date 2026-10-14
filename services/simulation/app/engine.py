from __future__ import annotations

import asyncio
import logging
import random
import signal as signal_module
import time

import grpc
from railway.ptc.v1 import common_pb2, telemetry_pb2, track_pb2
from railway.ptc.v1 import telemetry_pb2_grpc, track_pb2_grpc

from ptc_common.config import Settings
from ptc_common.db import Database
from ptc_common.topology import interpolate, progress_key, successors

from app.braking_link import BrakingLink
from app.repository import advance_tick, apply_motion, force_adhesion, load_world

log = logging.getLogger("ptc.simulation")

_SIGNAL_NAME = {
    int(common_pb2.ControlCommandOutput.PROCEED): "PROCEED",
    int(common_pb2.ControlCommandOutput.CAUTION): "CAUTION",
    int(common_pb2.ControlCommandOutput.STOP): "STOP",
    int(common_pb2.ControlCommandOutput.EMERGENCY_BRAKE): "EMERGENCY_BRAKE",
}


def integrate(
    speed_kmh: float,
    signal: str,
    cruise_kmh: float,
    max_decel: float,
    dt: float,
) -> tuple[float, str]:
    speed = max(0.0, speed_kmh) / 3.6
    if signal == "EMERGENCY_BRAKE":
        speed = max(0.0, speed - max_decel * dt)
        status = "EMERGENCY"
    elif signal == "STOP":
        speed = max(0.0, speed - 0.65 * max_decel * dt)
        status = "STOPPED" if speed < 0.4 else "RUNNING"
    elif signal == "CAUTION":
        cap = min(cruise_kmh, 45.0) / 3.6
        if speed > cap:
            speed = max(cap, speed - 0.5 * max_decel * dt)
        else:
            speed = min(cap, speed + 0.25 * dt)
        status = "CAUTION"
    else:
        cruise = max(0.0, cruise_kmh) / 3.6
        if speed < cruise:
            speed = min(cruise, speed + 0.4 * dt)
        else:
            speed = cruise
        status = "RUNNING"
    return speed * 3.6, status


def _signal_name(value: int) -> str:
    return _SIGNAL_NAME.get(int(value), "EMERGENCY_BRAKE")


def _pick_alert_block(trains: list[dict], blocks: dict[str, dict]) -> str | None:
    switch = blocks.get("M05", {}).get("switch_position", "NORMAL")
    candidates: list[str] = []
    for train in trains:
        cursor = successors(train["current_block_id"], switch)
        for _ in range(4):
            if not cursor:
                break
            block = blocks.get(cursor[0])
            if block and block["status"] == "FREE":
                candidates.append(block["block_id"])
            cursor = successors(cursor[0], switch)
    if not candidates:
        return None
    return random.choice(candidates)


class SimulationEngine:
    def __init__(self, cfg: Settings, db: Database) -> None:
        self.cfg = cfg
        self.db = db
        self.sequence = 0
        self.braking = BrakingLink(cfg.braking_addr)
        self.track_channel: grpc.aio.Channel | None = None
        self.telemetry_channel: grpc.aio.Channel | None = None
        self.track: track_pb2_grpc.TrackServiceStub | None = None
        self.telemetry: telemetry_pb2_grpc.TelemetryServiceStub | None = None
        self.stop = asyncio.Event()

    async def start(self) -> None:
        self.track_channel = grpc.aio.insecure_channel(self.cfg.track_addr)
        self.telemetry_channel = grpc.aio.insecure_channel(self.cfg.telemetry_addr)
        await self.track_channel.channel_ready()
        await self.telemetry_channel.channel_ready()
        self.track = track_pb2_grpc.TrackServiceStub(self.track_channel)
        self.telemetry = telemetry_pb2_grpc.TelemetryServiceStub(self.telemetry_channel)
        await self.braking.connect()
        log.info("motor de simulación conectado a vía, frenado y telemetría")

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal_module.SIGTERM, self.stop.set)
        except NotImplementedError:
            signal_module.signal(signal_module.SIGTERM, lambda *_: self.stop.set())
        await self.start()
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                await self._tick()
            except Exception:
                log.exception("el tick de simulación falló")
                await self.braking.connect()
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.05, self.cfg.tick_seconds - elapsed))

    async def _tick(self) -> None:
        assert self.track is not None and self.telemetry is not None
        trains, blocks, _meta = load_world(self.db)
        await self._stochastic(trains, blocks)
        order = sorted(
            trains,
            key=lambda train: progress_key(train["current_block_id"] or "", float(train["position_m"])),
            reverse=True,
        )
        samples = []
        for planned in order:
            if self.stop.is_set():
                return
            sample = await self._step_train(planned["train_id"])
            if sample is not None:
                samples.append(sample)
        if samples:
            try:
                await self.telemetry.IngestBatch(
                    telemetry_pb2.IngestBatchRequest(samples=samples),
                    timeout=3,
                )
            except Exception:
                log.exception("la ingesta de telemetría falló")
        tick = advance_tick(self.db)
        summary = ", ".join(
            f"{sample.train_id}:{sample.speed_kmh:.0f}km/h@{sample.block_id}/{sample.signal}"
            for sample in samples
        )
        log.info("tick %s | %s", tick, summary or "sin trenes")

    async def _stochastic(self, trains: list[dict], blocks: dict[str, dict]) -> None:
        assert self.track is not None
        if random.random() < 0.08:
            block_id = _pick_alert_block(trains, blocks)
            if block_id:
                ack = await self.track.SetBlockStatus(
                    track_pb2.SetBlockStatusRequest(
                        block_id=block_id,
                        status="ALERT",
                        hold_seconds=18,
                        reason=f"Ocupación estocástica del bloque {block_id}",
                    ),
                    timeout=3,
                )
                log.info("evento estocástico de vía: %s", ack.details)
        if random.random() < 0.04:
            candidates = [
                train["train_id"]
                for train in trains
                if float(train["adhesion_factor"]) >= 0.95 and not train["manual_hold"]
            ]
            if candidates:
                victim = random.choice(candidates)
                adhesion = random.uniform(0.35, 0.55)
                force_adhesion(self.db, victim, adhesion, random.randint(12, 24))

    async def _step_train(self, train_id: str):
        assert self.track is not None and self.telemetry is not None
        trains, blocks, _meta = load_world(self.db)
        train = next((item for item in trains if item["train_id"] == train_id), None)
        if train is None or not train["current_block_id"]:
            return None
        block = blocks.get(train["current_block_id"])
        if block is None:
            return None

        adhesion = float(train["adhesion_factor"])
        anomaly_until = train["anomaly_until"]
        if anomaly_until is not None and getattr(anomaly_until, "timestamp", None):
            if anomaly_until.timestamp() <= time.time():
                adhesion = 1.0

        self.sequence += 1
        now_ms = int(time.time() * 1000)
        latitude, longitude = interpolate(block, float(train["position_m"]))
        outgoing = common_pb2.TrainTelemetryInput(
            train_id=train_id,
            latitude=latitude,
            longitude=longitude,
            speed_kmh=float(train["speed_kmh"]),
            current_braking_distance=float(train["braking_distance_m"]),
            current_block_id=train["current_block_id"],
            timestamp=now_ms,
            position_m=float(train["position_m"]),
            adhesion_factor=adhesion,
            mass_kg=float(train["mass_kg"]),
            sequence=self.sequence,
            cruise_speed_kmh=float(train["cruise_speed_kmh"]),
            max_decel_mps2=float(train["max_decel_mps2"]),
        )
        command = await self.braking.exchange(outgoing, timeout=3)
        signal = _signal_name(command.signal)
        if train["manual_hold"]:
            signal = "EMERGENCY_BRAKE"
        previous_signal = train["signal"]
        old_speed = float(train["speed_kmh"])
        new_speed, status = integrate(
            old_speed,
            signal,
            float(train["cruise_speed_kmh"]),
            float(train["max_decel_mps2"]),
            self.cfg.tick_seconds,
        )
        if train["manual_hold"]:
            status = "EMERGENCY"
        delta_m = ((old_speed + new_speed) / 2.0) / 3.6 * self.cfg.tick_seconds
        proposed = float(train["position_m"]) + delta_m
        length = float(block["length_m"])
        target_block_id = train["current_block_id"]
        target_position = proposed
        target_lat, target_lon = interpolate(block, min(proposed, length - 0.5))

        if proposed >= length - 0.05:
            switch = blocks.get("M05", {}).get("switch_position", "NORMAL")
            nxt = successors(train["current_block_id"], switch)
            overflow = proposed - length
            target = blocks.get(nxt[0]) if nxt else None
            can_enter = target is not None and overflow < float(target["length_m"])
            if not can_enter:
                target_position = length - 1.0
                new_speed = 0.0
                if not train["manual_hold"]:
                    signal = "STOP"
                    status = "STOPPED"
                target_lat, target_lon = interpolate(block, target_position)
            else:
                entry = min(overflow, float(target["length_m"]) - 1.0)
                response = await self.track.OccupyBlock(
                    track_pb2.OccupyBlockRequest(
                        train_id=train_id,
                        block_id=target["block_id"],
                        entry_position_m=entry,
                        speed_kmh=new_speed,
                    ),
                    timeout=3,
                )
                if response.granted:
                    target_block_id = target["block_id"]
                    target_position = entry
                    target_lat, target_lon = interpolate(target, entry)
                else:
                    log.info("enclavamiento detuvo a %s: %s", train_id, response.details)
                    target_position = length - 1.0
                    new_speed = 0.0
                    if not train["manual_hold"]:
                        signal = "STOP"
                        status = "STOPPED"
                    target_lat, target_lon = interpolate(block, target_position)

        stored = apply_motion(
            self.db,
            train_id,
            speed_kmh=new_speed,
            position_m=target_position,
            latitude=target_lat,
            longitude=target_lon,
            status=status,
            signal=signal,
            braking_distance_m=float(command.braking_distance_m),
            distance_to_hazard_m=float(command.distance_to_hazard_m),
            adhesion_factor=adhesion,
            max_decel_mps2=float(train["max_decel_mps2"]),
            dt=self.cfg.tick_seconds,
        )
        if stored is None:
            return None
        if stored["signal"] != previous_signal:
            severity = "INFO"
            if stored["signal"] == "EMERGENCY_BRAKE":
                severity = "CRITICAL"
            elif stored["signal"] in {"STOP", "CAUTION"}:
                severity = "WARNING"
            try:
                await self.telemetry.RecordSafetyEvent(
                    common_pb2.SafetyEvent(
                        train_id=train_id,
                        block_id=stored["current_block_id"] or "",
                        event_type=f"SIGNAL_{stored['signal']}",
                        severity=severity,
                        message=command.message,
                        timestamp=now_ms,
                    ),
                    timeout=3,
                )
            except Exception:
                log.exception("no se pudo registrar el evento de %s", train_id)
        acceleration = ((float(stored["speed_kmh"]) - old_speed) / 3.6) / self.cfg.tick_seconds
        return telemetry_pb2.TelemetrySample(
            train_id=train_id,
            block_id=stored["current_block_id"] or target_block_id,
            latitude=float(stored["latitude"]),
            longitude=float(stored["longitude"]),
            speed_kmh=float(stored["speed_kmh"]),
            braking_distance_m=float(stored["braking_distance_m"]),
            acceleration_mps2=acceleration,
            timestamp=now_ms,
            signal=stored["signal"],
            distance_to_hazard_m=float(stored["distance_to_hazard_m"]),
        )
