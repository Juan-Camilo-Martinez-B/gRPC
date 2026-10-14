from __future__ import annotations

import logging

import grpc
from railway.ptc.v1 import common_pb2, simulation_pb2, telemetry_pb2, track_pb2
from railway.ptc.v1 import simulation_pb2_grpc, telemetry_pb2_grpc, track_pb2_grpc

from ptc_common.db import Database

log = logging.getLogger("ptc.dispatch")


class DispatchServicer:
    def __init__(self, db: Database, track_addr: str, simulation_addr: str, telemetry_addr: str) -> None:
        self.db = db
        self.track = track_pb2_grpc.TrackServiceStub(grpc.insecure_channel(track_addr))
        self.simulation = simulation_pb2_grpc.SimulationServiceStub(grpc.insecure_channel(simulation_addr))
        self.telemetry = telemetry_pb2_grpc.TelemetryServiceStub(grpc.insecure_channel(telemetry_addr))

    def handle(self, request) -> common_pb2.CommandAcknowledgment:
        operator = request.operator_id.strip() or "OCC"
        command = request.command_type.strip().upper()
        train_id = request.train_id.strip()
        try:
            if command == "EMERGENCY_STOP":
                ok, details = self._emergency(train_id or "*", operator)
            elif command == "RELEASE_TRAIN":
                ok, details = self._release(train_id or "*", operator)
            elif command in {"SWITCH_NORMAL", "SWITCH_REVERSE"}:
                ok, details = self._switch(command, request.target_id.strip() or "M05", operator)
            elif command == "SIMULATE_WEATHER":
                ok, details = self._weather(request, operator)
            else:
                ok, details = False, f"Comando no reconocido: {command}"
        except grpc.RpcError as exc:
            ok, details = False, f"El servicio interno rechazó la orden: {exc.details() or exc.code().name}"
            log.warning(details)
        command_id = self._store(request, operator, command, ok, details)
        if ok and command in {"EMERGENCY_STOP", "RELEASE_TRAIN"}:
            self._safety(train_id or "*", command, details)
        return common_pb2.CommandAcknowledgment(success=ok, details=details, command_id=command_id)

    def _emergency(self, train_id: str, operator: str) -> tuple[bool, str]:
        with self.db.transaction() as cur:
            if train_id == "*":
                cur.execute("SELECT train_id FROM trains ORDER BY train_id FOR UPDATE")
                found = [row["train_id"] for row in cur.fetchall()]
                if not found:
                    return False, "No hay trenes que detener"
                cur.execute(
                    """
                    UPDATE trains
                       SET manual_hold = TRUE,
                           status = 'EMERGENCY',
                           signal = 'EMERGENCY_BRAKE',
                           updated_at = now()
                    """
                )
                cur.execute("SELECT pg_notify('ptc_state', 'emergency')")
                return True, f"{operator} aplicó frenado de emergencia global sobre {', '.join(found)}"
            cur.execute(
                "SELECT train_id FROM trains WHERE train_id = %s FOR UPDATE",
                (train_id,),
            )
            if cur.fetchone() is None:
                return False, f"El tren {train_id} no existe"
            cur.execute(
                """
                UPDATE trains
                   SET manual_hold = TRUE,
                       status = 'EMERGENCY',
                       signal = 'EMERGENCY_BRAKE',
                       updated_at = now()
                 WHERE train_id = %s
                """,
                (train_id,),
            )
            cur.execute("SELECT pg_notify('ptc_state', 'emergency')")
            return True, f"{operator} aplicó frenado de emergencia a {train_id}"

    def _release(self, train_id: str, operator: str) -> tuple[bool, str]:
        with self.db.transaction() as cur:
            if train_id == "*":
                cur.execute("SELECT train_id FROM trains ORDER BY train_id FOR UPDATE")
                found = cur.fetchall()
                if not found:
                    return False, "No hay trenes que liberar"
                cur.execute(
                    """
                    UPDATE trains
                       SET manual_hold = FALSE,
                           status = CASE WHEN status = 'EMERGENCY' THEN 'RUNNING' ELSE status END,
                           signal = CASE WHEN signal = 'EMERGENCY_BRAKE' THEN 'CAUTION' ELSE signal END,
                           updated_at = now()
                    """
                )
            else:
                cur.execute(
                    "SELECT train_id FROM trains WHERE train_id = %s FOR UPDATE",
                    (train_id,),
                )
                if cur.fetchone() is None:
                    return False, f"El tren {train_id} no existe"
                cur.execute(
                    """
                    UPDATE trains
                       SET manual_hold = FALSE,
                           status = CASE WHEN status = 'EMERGENCY' THEN 'RUNNING' ELSE status END,
                           signal = CASE WHEN signal = 'EMERGENCY_BRAKE' THEN 'CAUTION' ELSE signal END,
                           updated_at = now()
                     WHERE train_id = %s
                    """,
                    (train_id,),
                )
            cur.execute("SELECT pg_notify('ptc_state', 'release')")
            target = "toda la flota" if train_id == "*" else train_id
            return True, f"{operator} liberó la retención manual de {target}"

    def _switch(self, command: str, block_id: str, operator: str) -> tuple[bool, str]:
        position = "NORMAL" if command == "SWITCH_NORMAL" else "REVERSE"
        ack = self.track.SetSwitch(
            track_pb2.SetSwitchRequest(
                block_id=block_id,
                position=position,
                operator_id=operator,
            ),
            timeout=3,
            wait_for_ready=True,
        )
        return ack.success, ack.details

    def _weather(self, request, operator: str) -> tuple[bool, str]:
        adhesion = request.parameter if 0 < request.parameter <= 1 else 0.30
        ack = self.simulation.InjectAnomaly(
            simulation_pb2.InjectAnomalyRequest(
                kind="WEATHER_ADHESION",
                train_id=request.train_id.strip(),
                adhesion_factor=adhesion,
                duration_seconds=30,
                operator_id=operator,
            ),
            timeout=3,
            wait_for_ready=True,
        )
        return ack.success, ack.details

    def _safety(self, train_id: str, command: str, details: str) -> None:
        severity = "CRITICAL" if command == "EMERGENCY_STOP" else "INFO"
        try:
            self.telemetry.RecordSafetyEvent(
                common_pb2.SafetyEvent(
                    train_id="" if train_id == "*" else train_id,
                    event_type=command,
                    severity=severity,
                    message=details,
                ),
                timeout=3,
            )
        except grpc.RpcError:
            log.exception("no se pudo registrar el evento de seguridad")

    def _store(self, request, operator: str, command: str, success: bool, details: str) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO dispatch_commands (
                    train_id, command_type, operator_id, target_id, parameter, status, details
                ) VALUES (%s, %s, %s, NULLIF(%s, ''), %s, %s, %s)
                RETURNING id
                """,
                (
                    request.train_id.strip() or None,
                    command,
                    operator,
                    request.target_id.strip(),
                    float(request.parameter),
                    "APPLIED" if success else "REJECTED",
                    details,
                ),
            )
            command_id = int(cur.fetchone()["id"])
            cur.execute("SELECT pg_notify('ptc_state', 'command')")
            return command_id
