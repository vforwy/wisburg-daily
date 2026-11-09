CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    institution TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    list_json TEXT,
    detail_json TEXT,
    content_hash TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    list_fetched_at TEXT,
    detail_fetched_at TEXT,
    updated_at TEXT NOT NULL,
    detail_status TEXT NOT NULL,
    UNIQUE (source, remote_id)
);

CREATE INDEX IF NOT EXISTS idx_items_source_published
    ON items (source, published_at);

CREATE TABLE IF NOT EXISTS checkpoints (
    source TEXT PRIMARY KEY,
    latest_id TEXT,
    latest_published_at TEXT,
    last_success_at TEXT,
    last_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_sources (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs (id),
    source TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    listed INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    detail_ok INTEGER NOT NULL DEFAULT 0,
    detail_fail INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title,
    body,
    institution,
    content='items',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts (rowid, title, body, institution)
    VALUES (new.id, new.title, new.body, new.institution);
END;

CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts (items_fts, rowid, title, body, institution)
    VALUES ('delete', old.id, old.title, old.body, old.institution);
END;

CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts (items_fts, rowid, title, body, institution)
    VALUES ('delete', old.id, old.title, old.body, old.institution);
    INSERT INTO items_fts (rowid, title, body, institution)
    VALUES (new.id, new.title, new.body, new.institution);
END;
