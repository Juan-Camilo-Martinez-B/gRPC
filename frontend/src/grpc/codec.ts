export type Scalar = "string" | "double" | "bool" | "int64";

export interface ScalarField {
  name: string;
  type: Scalar;
  repeated?: boolean;
}

export interface MessageField {
  name: string;
  type: "message";
  schema: Schema;
  repeated?: boolean;
}

export type Field = ScalarField | MessageField;
export type Schema = Record<number, Field>;
export type ProtoValue = string | number | boolean | ProtoObject | ProtoValue[] | null;
export interface ProtoObject {
  [key: string]: ProtoValue;
}

function readVarint(buffer: Uint8Array, offset: number): [number, number] {
  let value = 0;
  let shift = 0;
  let cursor = offset;
  while (cursor < buffer.length && shift <= 56) {
    const byte = buffer[cursor];
    cursor += 1;
    value += (byte & 0x7f) * 2 ** shift;
    if ((byte & 0x80) === 0) {
      return [value, cursor];
    }
    shift += 7;
  }
  throw new Error("Varint incompleto");
}

function writeVarint(value: number): number[] {
  const bytes: number[] = [];
  let remaining = Math.max(0, Math.floor(value));
  while (remaining > 127) {
    bytes.push((remaining % 128) + 128);
    remaining = Math.floor(remaining / 128);
  }
  bytes.push(remaining);
  return bytes;
}

function readDouble(buffer: Uint8Array, offset: number): [number, number] {
  const view = new DataView(buffer.buffer, buffer.byteOffset + offset, 8);
  return [view.getFloat64(0, true), offset + 8];
}

function skip(buffer: Uint8Array, offset: number, wire: number): number {
  if (wire === 0) return readVarint(buffer, offset)[1];
  if (wire === 1) return offset + 8;
  if (wire === 5) return offset + 4;
  if (wire === 2) {
    const [length, cursor] = readVarint(buffer, offset);
    return cursor + length;
  }
  throw new Error(`Wire type no soportado: ${wire}`);
}

function assign(target: ProtoObject, field: Field, value: ProtoValue): void {
  if (field.repeated) {
    const current = target[field.name];
    const list = Array.isArray(current) ? current : [];
    list.push(value);
    target[field.name] = list;
    return;
  }
  target[field.name] = value;
}

export function decodeMessage(buffer: Uint8Array, schema: Schema): ProtoObject {
  const result: ProtoObject = {};
  for (const field of Object.values(schema)) {
    if (field.repeated) result[field.name] = [];
    else if (field.type === "string") result[field.name] = "";
    else if (field.type === "bool") result[field.name] = false;
    else if (field.type === "message") result[field.name] = null;
    else result[field.name] = 0;
  }

  let offset = 0;
  while (offset < buffer.length) {
    const [tag, afterTag] = readVarint(buffer, offset);
    offset = afterTag;
    const fieldNumber = Math.floor(tag / 8);
    const wire = tag % 8;
    const field = schema[fieldNumber];
    if (!field) {
      offset = skip(buffer, offset, wire);
      continue;
    }
    if (wire === 0) {
      const [value, next] = readVarint(buffer, offset);
      offset = next;
      assign(result, field, field.type === "bool" ? value !== 0 : value);
    } else if (wire === 1) {
      const [value, next] = readDouble(buffer, offset);
      offset = next;
      assign(result, field, value);
    } else if (wire === 2) {
      const [length, next] = readVarint(buffer, offset);
      const slice = buffer.slice(next, next + length);
      offset = next + length;
      if (field.type === "string") {
        assign(result, field, new TextDecoder().decode(slice));
      } else if (field.type === "message") {
        assign(result, field, decodeMessage(slice, field.schema));
      }
    } else {
      offset = skip(buffer, offset, wire);
    }
  }
  return result;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function fieldBytes(fieldNumber: number, wire: number, payload: Uint8Array): Uint8Array {
  return concat([Uint8Array.from(writeVarint(fieldNumber * 8 + wire)), payload]);
}

export function fieldString(fieldNumber: number, value: string): Uint8Array {
  const encoded = new TextEncoder().encode(value);
  return fieldBytes(fieldNumber, 2, concat([Uint8Array.from(writeVarint(encoded.length)), encoded]));
}

export function fieldDouble(fieldNumber: number, value: number): Uint8Array {
  const payload = new Uint8Array(8);
  new DataView(payload.buffer).setFloat64(0, value, true);
  return fieldBytes(fieldNumber, 1, payload);
}

export function encodeDispatch(command: {
  trainId: string;
  commandType: string;
  operatorId: string;
  targetId?: string;
  parameter?: number;
}): Uint8Array {
  const parts = [
    fieldString(1, command.trainId),
    fieldString(2, command.commandType),
    fieldString(3, command.operatorId),
  ];
  if (command.targetId) parts.push(fieldString(4, command.targetId));
  if (command.parameter !== undefined) parts.push(fieldDouble(5, command.parameter));
  return concat(parts);
}
