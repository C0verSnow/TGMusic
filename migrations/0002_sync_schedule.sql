CREATE TABLE sync_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    interval_hours INTEGER NOT NULL DEFAULT 6 CHECK (interval_hours BETWEEN 1 AND 168),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    next_run INTEGER NOT NULL DEFAULT 0,
    last_dispatch INTEGER NOT NULL DEFAULT 0
);
INSERT INTO sync_schedule(id) VALUES(1);
