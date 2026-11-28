-- 正は back/src/db.py の SCHEMA。列を変えたら、このファイルは直さずに 0002_... を足す
CREATE TABLE IF NOT EXISTS drawings (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    image_1024_key TEXT NOT NULL,
    image_256_key  TEXT NOT NULL,
    strokes_key    TEXT NOT NULL,
    target         TEXT NOT NULL,
    duration_ms    INTEGER NOT NULL,
    stroke_count   INTEGER NOT NULL,
    point_count    INTEGER NOT NULL,
    sock_id        TEXT,
    font           TEXT,
    reading        TEXT,
    message        TEXT,
    user_name      TEXT,
    is_public      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS drawings_created_at ON drawings (created_at);