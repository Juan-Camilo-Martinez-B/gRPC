import { useEffect, useMemo, useState } from "react";
import {
  sendDispatchCommand,
  streamRailroadState,
  type BlockState,
  type RailroadState,
  type TrainState,
} from "./grpc/client";

const SIGNAL_LABEL: Record<string, string> = {
  PROCEED: "Vía libre",
  CAUTION: "Precaución",
  STOP: "Parada",
  EMERGENCY_BRAKE: "Freno de emergencia",
};

const STATUS_LABEL: Record<string, string> = {
  RUNNING: "En marcha",
  CAUTION: "Precaución",
  STOPPED: "Detenido",
  EMERGENCY: "Emergencia",
  FREE: "Libre",
  OCCUPIED: "Ocupado",
  ALERT: "Alerta",
  MAINTENANCE: "Mantenimiento",
};

const KIND_LABEL: Record<string, string> = {
  EXPRESS: "Expreso",
  REGIONAL: "Regional",
  FREIGHT: "Carga",
};

function label(table: Record<string, string>, value: string): string {
  return table[value] ?? value;
}

function clock(timestamp: number): string {
  if (!timestamp) return "--:--:--";
  return new Date(timestamp).toLocaleTimeString("es-CO", { hour12: false });
}

function toneOf(block: BlockState, trains: TrainState[]): string {
  const train = trains.find((item) => item.blockId === block.blockId);
  if (block.status === "MAINTENANCE") return "maintenance";
  if (
    block.status === "ALERT" ||
    train?.signal === "EMERGENCY_BRAKE" ||
    train?.signal === "STOP" ||
    train?.status === "EMERGENCY"
  ) {
    return "alert";
  }
  if (train?.signal === "CAUTION" || train?.status === "CAUTION") return "caution";
  if (block.isOccupied || block.status === "OCCUPIED") return "occupied";
  return "free";
}

function BlockCard({ block, trains }: { block: BlockState; trains: TrainState[] }) {
  const occupants = trains.filter((train) => train.blockId === block.blockId);
  return (
    <article className={`block ${toneOf(block, trains)}`}>
      <header>
        <strong>{block.blockId}</strong>
        <span>{label(STATUS_LABEL, block.status)}</span>
      </header>
      <div className="rails" aria-hidden="true">
        <i />
        <i />
      </div>
      {occupants.map((train) => (
        <div
          key={train.trainId}
          className={`train-chip ${train.signal === "EMERGENCY_BRAKE" || train.status === "EMERGENCY" ? "alarm" : ""}`}
          style={{ left: `${Math.min(92, Math.max(4, (train.positionM / block.lengthM) * 100))}%` }}
          title={`${train.name} · ${train.speed.toFixed(0)} km/h`}
        >
          {train.trainId}
        </div>
      ))}
      <footer>
        <span>{block.gradePercent > 0 ? `↓ ${block.gradePercent.toFixed(1)}%` : block.gradePercent < 0 ? `↑ ${Math.abs(block.gradePercent).toFixed(1)}%` : "0%"}</span>
        {block.switchPosition !== "NONE" && <span>Aguja {block.switchPosition === "REVERSE" ? "desvío" : "normal"}</span>}
        {block.occupiedBy && <span>{block.occupiedBy}</span>}
      </footer>
    </article>
  );
}

export function App() {
  const [state, setState] = useState<RailroadState | null>(null);
  const [link, setLink] = useState("conectando");
  const [linkError, setLinkError] = useState("");
  const [operatorId, setOperatorId] = useState("despachador.occ");
  const [pending, setPending] = useState("");
  const [notice, setNotice] = useState("Panel OCC listo. El stream gRPC-Web aún no entrega estado.");

  useEffect(() => {
    const abort = new AbortController();
    let attempt = 0;
    const run = async () => {
      while (!abort.signal.aborted) {
        try {
          setLink("conectando");
          await streamRailroadState((next) => {
            if (abort.signal.aborted) return;
            setState(next);
            setLink("en vivo");
            setLinkError("");
            attempt = 0;
          }, abort.signal);
          if (abort.signal.aborted) return;
          setLink("reintentando");
        } catch (error) {
          if (abort.signal.aborted) return;
          const message = error instanceof Error ? error.message : "fallo de stream";
          if (message.includes("aborted") || message.includes("Abort")) return;
          setLink("reintentando");
          setLinkError(message);
        }
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, Math.min(5000, 600 * attempt)));
      }
    };
    void run();
    return () => abort.abort();
  }, []);

  const mainBlocks = useMemo(
    () => (state?.blocks ?? []).filter((block) => block.lineId === "MAIN").sort((a, b) => a.sequence - b.sequence),
    [state],
  );
  const sidingBlocks = useMemo(
    () => (state?.blocks ?? []).filter((block) => block.lineId === "SIDING").sort((a, b) => a.sequence - b.sequence),
    [state],
  );
  const switchBlock = mainBlocks.find((block) => block.switchPosition !== "NONE");
  const trains = state?.trains ?? [];
  const emergencyCount = trains.filter((train) => train.manualHold || train.signal === "EMERGENCY_BRAKE" || train.status === "EMERGENCY").length;
  const occupiedCount = (state?.blocks ?? []).filter((block) => block.isOccupied || block.status === "OCCUPIED" || block.status === "ALERT").length;

  async function command(action: string, input: { trainId: string; commandType: string; targetId?: string; parameter?: number }) {
    setPending(action);
    try {
      const ack = await sendDispatchCommand({ ...input, operatorId: operatorId.trim() || "OCC" });
      setNotice(ack.details || (ack.success ? "Orden aplicada" : "Orden rechazada"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo enviar la orden");
    } finally {
      setPending("");
    }
  }

  return (
    <div className="occ">
      <header className="topbar">
        <div>
          <p className="eyebrow">Plataforma PTC · gRPC-Web / HTTP/2</p>
          <h1>Centro de Control de Operaciones</h1>
        </div>
        <div className="top-meta">
          <span className={`live ${link === "en vivo" ? "on" : "off"}`}>{link}</span>
          <span>Tick {state?.tick ?? 0}</span>
          <span>{clock(state?.timestamp ?? 0)}</span>
          <span>{state?.weather ?? "SIN ENLACE"}</span>
        </div>
      </header>

      {linkError && <p className="banner warn">Stream interrumpido: {linkError}. Reintentando contra Envoy en el puerto 8080.</p>}

      <section className="metrics">
        <article>
          <span>Trenes</span>
          <strong>{trains.length}</strong>
        </article>
        <article>
          <span>Bloques ocupados o en alerta</span>
          <strong>{occupiedCount}</strong>
        </article>
        <article>
          <span>Protecciones activas</span>
          <strong>{emergencyCount}</strong>
        </article>
        <article>
          <span>Simulación</span>
          <strong>{state?.simulationRunning ? "AUTÓNOMA" : "DETENIDA"}</strong>
        </article>
      </section>

      <main className="workspace">
        <section className="panel diagram">
          <div className="panel-head">
            <h2>Corredor central</h2>
            <ul className="legend">
              <li><i className="swatch free" /> Libre</li>
              <li><i className="swatch occupied" /> Ocupado</li>
              <li><i className="swatch caution" /> Precaución</li>
              <li><i className="swatch alert" /> Alerta</li>
              <li><i className="swatch maintenance" /> Mantenimiento</li>
            </ul>
          </div>
          <div className="line">
            {mainBlocks.map((block) => (
              <BlockCard key={block.blockId} block={block} trains={trains} />
            ))}
          </div>
          <div className="line siding">
            <div className="spacer before" />
            {sidingBlocks.map((block) => (
              <BlockCard key={block.blockId} block={block} trains={trains} />
            ))}
            <div className="spacer after" />
          </div>
          <p className="hint">
            Vía principal M01–M10. La aguja de M05 en posición normal continúa hacia M06; en desvío entra al apartadero S01–S03 y reingresa en M07.
          </p>
        </section>

        <aside className="panel controls">
          <h2>Intervención manual</h2>
          <label>
            Operador
            <input value={operatorId} onChange={(event) => setOperatorId(event.target.value)} maxLength={40} />
          </label>
          <div className="actions">
            <button className="danger" disabled={pending !== ""} onClick={() => void command("global-stop", { trainId: "*", commandType: "EMERGENCY_STOP" })}>
              Frenado de emergencia global
            </button>
            <button disabled={pending !== ""} onClick={() => void command("global-release", { trainId: "*", commandType: "RELEASE_TRAIN" })}>
              Liberar retención de la flota
            </button>
            <button className="weather" disabled={pending !== ""} onClick={() => void command("weather", { trainId: "", commandType: "SIMULATE_WEATHER", parameter: 0.3 })}>
              Simular anomalía climática
            </button>
            <button disabled={pending !== "" || !switchBlock} onClick={() => void command("switch-normal", { trainId: "", commandType: "SWITCH_NORMAL", targetId: switchBlock?.blockId ?? "M05" })}>
              Aguja {switchBlock?.blockId ?? "M05"} a normal
            </button>
            <button disabled={pending !== "" || !switchBlock} onClick={() => void command("switch-reverse", { trainId: "", commandType: "SWITCH_REVERSE", targetId: switchBlock?.blockId ?? "M05" })}>
              Aguja {switchBlock?.blockId ?? "M05"} a desvío
            </button>
          </div>
          <p className="notice">{pending ? "Enviando orden por gRPC-Web…" : notice}</p>

          <h2>Flota</h2>
          <div className="trains">
            {trains.map((train) => (
              <article key={train.trainId} className={train.manualHold ? "held" : ""}>
                <header>
                  <strong>{train.trainId}</strong>
                  <span>{label(KIND_LABEL, train.kind)}</span>
                </header>
                <p>{train.name}</p>
                <dl>
                  <div><dt>Velocidad</dt><dd>{train.speed.toFixed(1)} km/h</dd></div>
                  <div><dt>Bloque</dt><dd>{train.blockId} · {train.positionM.toFixed(0)} m</dd></div>
                  <div><dt>Señal</dt><dd>{label(SIGNAL_LABEL, train.signal)}</dd></div>
                  <div><dt>Estado</dt><dd>{label(STATUS_LABEL, train.status)}{train.manualHold ? " · retención OCC" : ""}</dd></div>
                  <div><dt>Frenado</dt><dd>{train.brakingDistanceM.toFixed(0)} m</dd></div>
                  <div><dt>Autoridad</dt><dd>{train.distanceToHazardM.toFixed(0)} m</dd></div>
                  <div><dt>Adherencia</dt><dd>{train.adhesion.toFixed(2)}</dd></div>
                  <div><dt>Posición</dt><dd>{train.latitude.toFixed(5)}°, {train.longitude.toFixed(5)}°</dd></div>
                </dl>
                <div className="row-actions">
                  <button className="danger" disabled={pending !== ""} onClick={() => void command(`stop-${train.trainId}`, { trainId: train.trainId, commandType: "EMERGENCY_STOP" })}>
                    Frenar
                  </button>
                  <button disabled={pending !== ""} onClick={() => void command(`release-${train.trainId}`, { trainId: train.trainId, commandType: "RELEASE_TRAIN" })}>
                    Liberar
                  </button>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </main>

      <section className="panel log">
        <h2>Terminal de seguridad</h2>
        <div className="log-grid">
          <ol>
            {(state?.events ?? []).map((event) => (
              <li key={event.id} className={event.severity.toLowerCase()}>
                <time>{clock(event.timestamp)}</time>
                <em>{event.severity}</em>
                <span>{event.trainId || "SISTEMA"} {event.blockId && `· ${event.blockId}`}</span>
                <p>{event.message}</p>
              </li>
            ))}
          </ol>
          <ol>
            {(state?.commands ?? []).map((command) => (
              <li key={command.id} className={command.status === "APPLIED" ? "info" : "warning"}>
                <time>{clock(command.timestamp)}</time>
                <em>{command.status}</em>
                <span>{command.commandType} · {command.operatorId}</span>
                <p>{command.details}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}
