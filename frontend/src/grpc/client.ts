import { decodeMessage, encodeDispatch, type ProtoObject, type Schema } from "./codec";

const endpoint = (import.meta.env.VITE_GRPC_WEB_URL ?? "http://localhost:8080").replace(/\/$/, "");

const trainSchema: Schema = {
  1: { name: "trainId", type: "string" },
  2: { name: "speed", type: "double" },
  3: { name: "blockId", type: "string" },
  4: { name: "status", type: "string" },
  5: { name: "name", type: "string" },
  6: { name: "latitude", type: "double" },
  7: { name: "longitude", type: "double" },
  8: { name: "positionM", type: "double" },
  9: { name: "signal", type: "string" },
  10: { name: "brakingDistanceM", type: "double" },
  11: { name: "adhesion", type: "double" },
  12: { name: "manualHold", type: "bool" },
  13: { name: "kind", type: "string" },
  14: { name: "distanceToHazardM", type: "double" },
};

const blockSchema: Schema = {
  1: { name: "blockId", type: "string" },
  2: { name: "isOccupied", type: "bool" },
  3: { name: "occupiedBy", type: "string" },
  4: { name: "status", type: "string" },
  5: { name: "lineId", type: "string" },
  6: { name: "sequence", type: "int64" },
  7: { name: "signalAspect", type: "string" },
  8: { name: "gradePercent", type: "double" },
  9: { name: "lengthM", type: "double" },
  10: { name: "switchPosition", type: "string" },
  11: { name: "latitudeStart", type: "double" },
  12: { name: "longitudeStart", type: "double" },
  13: { name: "latitudeEnd", type: "double" },
  14: { name: "longitudeEnd", type: "double" },
};

const eventSchema: Schema = {
  1: { name: "id", type: "int64" },
  2: { name: "trainId", type: "string" },
  3: { name: "blockId", type: "string" },
  4: { name: "eventType", type: "string" },
  5: { name: "severity", type: "string" },
  6: { name: "message", type: "string" },
  7: { name: "timestamp", type: "int64" },
};

const commandSchema: Schema = {
  1: { name: "id", type: "int64" },
  2: { name: "trainId", type: "string" },
  3: { name: "commandType", type: "string" },
  4: { name: "operatorId", type: "string" },
  5: { name: "status", type: "string" },
  6: { name: "details", type: "string" },
  7: { name: "timestamp", type: "int64" },
  8: { name: "targetId", type: "string" },
};

const stateSchema: Schema = {
  1: { name: "trains", type: "message", schema: trainSchema, repeated: true },
  2: { name: "blocks", type: "message", schema: blockSchema, repeated: true },
  3: { name: "tick", type: "int64" },
  4: { name: "timestamp", type: "int64" },
  5: { name: "events", type: "message", schema: eventSchema, repeated: true },
  6: { name: "commands", type: "message", schema: commandSchema, repeated: true },
  7: { name: "weather", type: "string" },
  8: { name: "simulationRunning", type: "bool" },
};

const ackSchema: Schema = {
  1: { name: "success", type: "bool" },
  2: { name: "details", type: "string" },
  3: { name: "commandId", type: "int64" },
};

export interface TrainState {
  trainId: string;
  speed: number;
  blockId: string;
  status: string;
  name: string;
  latitude: number;
  longitude: number;
  positionM: number;
  signal: string;
  brakingDistanceM: number;
  adhesion: number;
  manualHold: boolean;
  kind: string;
  distanceToHazardM: number;
}

export interface BlockState {
  blockId: string;
  isOccupied: boolean;
  occupiedBy: string;
  status: string;
  lineId: string;
  sequence: number;
  signalAspect: string;
  gradePercent: number;
  lengthM: number;
  switchPosition: string;
}

export interface SafetyEvent {
  id: number;
  trainId: string;
  blockId: string;
  eventType: string;
  severity: string;
  message: string;
  timestamp: number;
}

export interface CommandRecord {
  id: number;
  trainId: string;
  commandType: string;
  operatorId: string;
  status: string;
  details: string;
  timestamp: number;
  targetId: string;
}

export interface RailroadState {
  tick: number;
  timestamp: number;
  weather: string;
  simulationRunning: boolean;
  trains: TrainState[];
  blocks: BlockState[];
  events: SafetyEvent[];
  commands: CommandRecord[];
}

export interface CommandAck {
  success: boolean;
  details: string;
  commandId: number;
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function bool(value: unknown): boolean {
  return value === true;
}

function objects(value: unknown): ProtoObject[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ProtoObject => typeof item === "object" && item !== null && !Array.isArray(item));
}

export function toRailroadState(raw: ProtoObject): RailroadState {
  return {
    tick: num(raw.tick),
    timestamp: num(raw.timestamp),
    weather: str(raw.weather) || "DESPEJADO",
    simulationRunning: bool(raw.simulationRunning),
    trains: objects(raw.trains).map((train) => ({
      trainId: str(train.trainId),
      speed: num(train.speed),
      blockId: str(train.blockId),
      status: str(train.status),
      name: str(train.name),
      latitude: num(train.latitude),
      longitude: num(train.longitude),
      positionM: num(train.positionM),
      signal: str(train.signal),
      brakingDistanceM: num(train.brakingDistanceM),
      adhesion: num(train.adhesion),
      manualHold: bool(train.manualHold),
      kind: str(train.kind),
      distanceToHazardM: num(train.distanceToHazardM),
    })),
    blocks: objects(raw.blocks).map((block) => ({
      blockId: str(block.blockId),
      isOccupied: bool(block.isOccupied),
      occupiedBy: str(block.occupiedBy),
      status: str(block.status),
      lineId: str(block.lineId),
      sequence: num(block.sequence),
      signalAspect: str(block.signalAspect),
      gradePercent: num(block.gradePercent),
      lengthM: num(block.lengthM) || 1,
      switchPosition: str(block.switchPosition),
    })),
    events: objects(raw.events).map((event) => ({
      id: num(event.id),
      trainId: str(event.trainId),
      blockId: str(event.blockId),
      eventType: str(event.eventType),
      severity: str(event.severity),
      message: str(event.message),
      timestamp: num(event.timestamp),
    })),
    commands: objects(raw.commands).map((command) => ({
      id: num(command.id),
      trainId: str(command.trainId),
      commandType: str(command.commandType),
      operatorId: str(command.operatorId),
      status: str(command.status),
      details: str(command.details),
      timestamp: num(command.timestamp),
      targetId: str(command.targetId),
    })),
  };
}

interface Frame {
  flag: number;
  payload: Uint8Array;
}

function readFrames(buffer: Uint8Array): Frame[] {
  const frames: Frame[] = [];
  let offset = 0;
  while (offset + 5 <= buffer.length) {
    const flag = buffer[offset];
    const length = buffer[offset + 1] * 16777216 + buffer[offset + 2] * 65536 + buffer[offset + 3] * 256 + buffer[offset + 4];
    if (offset + 5 + length > buffer.length) break;
    frames.push({ flag, payload: buffer.slice(offset + 5, offset + 5 + length) });
    offset += 5 + length;
  }
  return frames;
}

function assertTrailer(payload: Uint8Array): void {
  const text = new TextDecoder().decode(payload);
  const status = text.match(/grpc-status:\s*(\d+)/);
  if (status && status[1] !== "0") {
    const message = text.match(/grpc-message:\s*([^\r\n]*)/);
    throw new Error(decodeURIComponent((message?.[1] ?? "error gRPC").replace(/\+/g, " ")));
  }
}

async function decodeBody(response: Response): Promise<Uint8Array> {
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("grpc-web-text")) {
    const text = (await response.text()).replace(/\s/g, "");
    const binary = atob(text);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  }
  return new Uint8Array(await response.arrayBuffer());
}

async function* streamFrames(body: ReadableStream<Uint8Array>): AsyncGenerator<Frame> {
  const reader = body.getReader();
  let pending = new Uint8Array(0);
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (value && value.length > 0) {
        const merged = new Uint8Array(pending.length + value.length);
        merged.set(pending);
        merged.set(value, pending.length);
        pending = merged;
      }
      while (pending.length >= 5) {
        const length = pending[1] * 16777216 + pending[2] * 65536 + pending[3] * 256 + pending[4];
        if (pending.length < 5 + length) break;
        yield { flag: pending[0], payload: pending.slice(5, 5 + length) };
        pending = pending.slice(5 + length);
      }
      if (done) return;
    }
  } finally {
    reader.releaseLock();
  }
}

function grpcFrame(payload: Uint8Array): Uint8Array {
  const frame = new Uint8Array(5 + payload.byteLength);
  new DataView(frame.buffer).setUint32(1, payload.byteLength, false);
  frame.set(payload, 5);
  return frame;
}

function requestBody(bytes: Uint8Array): ArrayBuffer {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

async function grpcPost(path: string, body: Uint8Array, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(`${endpoint}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/grpc-web+proto",
      Accept: "application/grpc-web+proto",
      "X-Grpc-Web": "1",
      "X-User-Agent": "ptc-occ",
    },
    body: requestBody(grpcFrame(body)),
    signal,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} en ${path}`);
  }
  const status = response.headers.get("grpc-status");
  if (status && status !== "0") {
    throw new Error(response.headers.get("grpc-message") ?? `gRPC ${status}`);
  }
  return response;
}

export async function streamRailroadState(
  onState: (state: RailroadState) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await grpcPost("/railway.ptc.v1.TelemetryService/StreamRailroadState", new Uint8Array(), signal);
  if (!response.body) throw new Error("El stream gRPC-Web no entregó cuerpo");
  for await (const frame of streamFrames(response.body)) {
    if ((frame.flag & 0x80) !== 0) {
      assertTrailer(frame.payload);
      continue;
    }
    onState(toRailroadState(decodeMessage(frame.payload, stateSchema)));
  }
}

export async function sendDispatchCommand(input: {
  trainId: string;
  commandType: string;
  operatorId: string;
  targetId?: string;
  parameter?: number;
}): Promise<CommandAck> {
  const response = await grpcPost(
    "/railway.ptc.v1.DispatchService/SendDispatchCommand",
    encodeDispatch(input),
  );
  const frames = readFrames(await decodeBody(response));
  for (const frame of frames) {
    if ((frame.flag & 0x80) !== 0) assertTrailer(frame.payload);
  }
  const data = frames.find((frame) => (frame.flag & 0x80) === 0);
  if (!data) throw new Error("Dispatch no devolvió un acuse");
  const ack = decodeMessage(data.payload, ackSchema);
  return {
    success: bool(ack.success),
    details: str(ack.details),
    commandId: num(ack.commandId),
  };
}
