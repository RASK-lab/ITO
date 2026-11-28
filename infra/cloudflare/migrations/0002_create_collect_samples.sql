-- 正は back/src/db.py の SCHEMA（collect_samples の部分）。列を変えたら 0003_... を足す
CREATE TABLE IF NOT EXISTS collect_samples (
    id                 TEXT PRIMARY KEY,
    created_at         TEXT NOT NULL,
    protocol           TEXT NOT NULL,
    writer_id          TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    trial              INTEGER NOT NULL,
    condition          TEXT NOT NULL,
    instruction        TEXT NOT NULL,
    dominant_hand      TEXT NOT NULL,
    calligraphy        TEXT NOT NULL,
    pointer_type       TEXT NOT NULL,
    display_px         INTEGER NOT NULL,
    device_pixel_ratio REAL NOT NULL,
    redo_count         INTEGER NOT NULL,
    target             TEXT NOT NULL,
    duration_ms        INTEGER NOT NULL,
    stroke_count       INTEGER NOT NULL,
    point_count        INTEGER NOT NULL,
    image_1024_key     TEXT NOT NULL,
    image_256_key      TEXT NOT NULL,
    strokes_json       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS collect_samples_condition ON collect_samples (condition, pointer_type);