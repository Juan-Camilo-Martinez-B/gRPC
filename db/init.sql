-- Esquema centralizado de la PTC.
-- Todos los microservicios usan esta misma base. La integridad entre
-- escritores concurrentes se apoya en transacciones ACID y en
-- SELECT ... FOR UPDATE (ver servicios Track, Simulation y Dispatch).
-- Orden de bloqueo obligatorio: railway_blocks (block_id ASC) y después
-- trains (train_id ASC).

CREATE TABLE railway_blocks (
    block_id              TEXT PRIMARY KEY,
    line_id               TEXT NOT NULL,
    sequence_order        INTEGER NOT NULL,
    length_m              DOUBLE PRECISION NOT NULL CHECK (length_m > 0),
    grade_percent         DOUBLE PRECISION NOT NULL DEFAULT 0,
    latitude_start        DOUBLE PRECISION NOT NULL,
    longitude_start       DOUBLE PRECISION NOT NULL,
    latitude_end          DOUBLE PRECISION NOT NULL,
    longitude_end         DOUBLE PRECISION NOT NULL,
    status                TEXT NOT NULL DEFAULT 'FREE'
                          CHECK (status IN ('FREE', 'OCCUPIED', 'MAINTENANCE', 'ALERT')),
    occupied_by_train_id  TEXT,
    signal_aspect         TEXT NOT NULL DEFAULT 'PROCEED'
                          CHECK (signal_aspect IN ('PROCEED', 'CAUTION', 'STOP', 'EMERGENCY_BRAKE')),
    switch_position       TEXT NOT NULL DEFAULT 'NONE'
                          CHECK (switch_position IN ('NONE', 'NORMAL', 'REVERSE')),
    hold_until            TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (line_id, sequence_order)
);

CREATE TABLE trains (
    train_id              TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    kind                  TEXT NOT NULL CHECK (kind IN ('EXPRESS', 'REGIONAL', 'FREIGHT')),
    mass_kg               DOUBLE PRECISION NOT NULL CHECK (mass_kg > 0),
    length_m              DOUBLE PRECISION NOT NULL CHECK (length_m > 0),
    max_decel_mps2        DOUBLE PRECISION NOT NULL CHECK (max_decel_mps2 > 0),
    cruise_speed_kmh      DOUBLE PRECISION NOT NULL CHECK (cruise_speed_kmh > 0),
    speed_kmh             DOUBLE PRECISION NOT NULL CHECK (speed_kmh >= 0),
    position_m            DOUBLE PRECISION NOT NULL CHECK (position_m >= 0),
    latitude              DOUBLE PRECISION NOT NULL,
    longitude             DOUBLE PRECISION NOT NULL,
    current_block_id      TEXT REFERENCES railway_blocks (block_id),
    status                TEXT NOT NULL CHECK (status IN ('RUNNING', 'CAUTION', 'STOPPED', 'EMERGENCY')),
    signal                TEXT NOT NULL CHECK (signal IN ('PROCEED', 'CAUTION', 'STOP', 'EMERGENCY_BRAKE')),
    adhesion_factor       DOUBLE PRECISION NOT NULL DEFAULT 1 CHECK (adhesion_factor > 0 AND adhesion_factor <= 1),
    anomaly_until         TIMESTAMPTZ,
    braking_distance_m    DOUBLE PRECISION NOT NULL DEFAULT 0,
    distance_to_hazard_m  DOUBLE PRECISION NOT NULL DEFAULT 0,
    manual_hold           BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE railway_blocks
    ADD CONSTRAINT railway_blocks_train_fk
    FOREIGN KEY (occupied_by_train_id) REFERENCES trains (train_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE telemetry_logs (
    id                    BIGSERIAL PRIMARY KEY,
    train_id              TEXT NOT NULL REFERENCES trains (train_id),
    block_id              TEXT REFERENCES railway_blocks (block_id),
    latitude              DOUBLE PRECISION NOT NULL,
    longitude             DOUBLE PRECISION NOT NULL,
    speed_kmh             DOUBLE PRECISION NOT NULL,
    braking_distance_m    DOUBLE PRECISION NOT NULL,
    distance_to_hazard_m  DOUBLE PRECISION NOT NULL DEFAULT 0,
    acceleration_mps2     DOUBLE PRECISION NOT NULL DEFAULT 0,
    signal                TEXT NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX telemetry_logs_train_time_idx
    ON telemetry_logs (train_id, recorded_at DESC);

CREATE TABLE dispatch_commands (
    id              BIGSERIAL PRIMARY KEY,
    train_id        TEXT,
    command_type    TEXT NOT NULL,
    operator_id     TEXT NOT NULL,
    target_id       TEXT,
    parameter       DOUBLE PRECISION,
    status          TEXT NOT NULL CHECK (status IN ('APPLIED', 'REJECTED')),
    details         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX dispatch_commands_time_idx
    ON dispatch_commands (created_at DESC);

CREATE TABLE safety_events (
    id            BIGSERIAL PRIMARY KEY,
    train_id      TEXT,
    block_id      TEXT,
    event_type    TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    message       TEXT NOT NULL,
    signal_status TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX safety_events_time_idx
    ON safety_events (created_at DESC);

CREATE TABLE simulation_meta (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    tick        BIGINT NOT NULL DEFAULT 0,
    running     BOOLEAN NOT NULL DEFAULT TRUE,
    weather     TEXT NOT NULL DEFAULT 'DESPEJADO',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Un tren no puede quedar asociado a un bloque inhabilitado por mantenimiento.
CREATE OR REPLACE FUNCTION reject_disabled_block() RETURNS trigger AS $$
DECLARE
    block_status TEXT;
BEGIN
    IF NEW.current_block_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT status INTO block_status
      FROM railway_blocks
     WHERE block_id = NEW.current_block_id;
    IF block_status = 'MAINTENANCE' THEN
        RAISE EXCEPTION 'Bloque % inhabilitado por mantenimiento', NEW.current_block_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trains_reject_disabled_block
    BEFORE INSERT OR UPDATE OF current_block_id ON trains
    FOR EACH ROW
    EXECUTE FUNCTION reject_disabled_block();

-- grade_percent > 0 significa pendiente descendente en sentido de la marcha
-- (aumenta la distancia de frenado). Cada bloque mide 800 m.
-- Corredor ficticio sobre la sabana de Bogotá.

INSERT INTO railway_blocks (
    block_id, line_id, sequence_order, length_m, grade_percent,
    latitude_start, longitude_start, latitude_end, longitude_end,
    status, switch_position, signal_aspect
) VALUES
    ('M01', 'MAIN', 1, 800,  0.2, 4.6500, -74.1200, 4.6570, -74.1160, 'FREE', 'NONE', 'PROCEED'),
    ('M02', 'MAIN', 2, 800, -0.4, 4.6570, -74.1160, 4.6640, -74.1120, 'FREE', 'NONE', 'PROCEED'),
    ('M03', 'MAIN', 3, 800,  0.6, 4.6640, -74.1120, 4.6710, -74.1080, 'FREE', 'NONE', 'PROCEED'),
    ('M04', 'MAIN', 4, 800,  1.4, 4.6710, -74.1080, 4.6780, -74.1040, 'FREE', 'NONE', 'PROCEED'),
    ('M05', 'MAIN', 5, 800,  0.3, 4.6780, -74.1040, 4.6850, -74.1000, 'FREE', 'NORMAL', 'PROCEED'),
    ('M06', 'MAIN', 6, 800, -0.7, 4.6850, -74.1000, 4.6920, -74.0960, 'FREE', 'NONE', 'PROCEED'),
    ('M07', 'MAIN', 7, 800,  0.4, 4.6920, -74.0960, 4.6990, -74.0920, 'FREE', 'NONE', 'PROCEED'),
    ('M08', 'MAIN', 8, 800,  1.1, 4.6990, -74.0920, 4.7060, -74.0880, 'FREE', 'NONE', 'PROCEED'),
    ('M09', 'MAIN', 9, 800, -0.2, 4.7060, -74.0880, 4.7130, -74.0840, 'FREE', 'NONE', 'PROCEED'),
    ('M10', 'MAIN',10, 800,  0.0, 4.7130, -74.0840, 4.7200, -74.0800, 'FREE', 'NONE', 'PROCEED'),
    ('S01', 'SIDING', 1, 800, 0.5, 4.6765, -74.1030, 4.6815, -74.0995, 'FREE', 'NONE', 'PROCEED'),
    ('S02', 'SIDING', 2, 800, 0.5, 4.6815, -74.0995, 4.6865, -74.0960, 'FREE', 'NONE', 'PROCEED'),
    ('S03', 'SIDING', 3, 800,-0.3, 4.6865, -74.0960, 4.6920, -74.0920, 'FREE', 'NONE', 'PROCEED');

INSERT INTO trains (
    train_id, name, kind, mass_kg, length_m, max_decel_mps2, cruise_speed_kmh,
    speed_kmh, position_m, latitude, longitude, current_block_id,
    status, signal, adhesion_factor
) VALUES
    ('EXP-01', 'Express Andino',   'EXPRESS',  160000, 120, 1.15, 160, 150, 400, 4.6675, -74.1100, 'M03', 'RUNNING', 'PROCEED', 1),
    ('REG-14', 'Regional Sabana',  'REGIONAL', 240000, 160, 0.95, 110,  55, 200, 4.6798, -74.1030, 'M05', 'RUNNING', 'PROCEED', 1),
    ('FRG-09', 'Carga Nevado',     'FREIGHT',  920000, 420, 0.55,  80,  45, 120, 4.7001, -74.0914, 'M08', 'RUNNING', 'PROCEED', 1);

UPDATE railway_blocks SET status = 'OCCUPIED', occupied_by_train_id = 'EXP-01', signal_aspect = 'PROCEED'
 WHERE block_id = 'M03';
UPDATE railway_blocks SET status = 'OCCUPIED', occupied_by_train_id = 'REG-14', signal_aspect = 'PROCEED'
 WHERE block_id = 'M05';
UPDATE railway_blocks SET status = 'OCCUPIED', occupied_by_train_id = 'FRG-09', signal_aspect = 'PROCEED'
 WHERE block_id = 'M08';

INSERT INTO simulation_meta (id, tick, running, weather) VALUES (1, 0, TRUE, 'DESPEJADO');

INSERT INTO safety_events (train_id, block_id, event_type, severity, message, signal_status)
VALUES
    (NULL, NULL, 'SYSTEM_START', 'INFO',
     'Base PTC inicializada. Corredor principal M01–M10 y apartadero S01–S03.',
     'PROCEED');
