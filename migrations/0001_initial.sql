CREATE TABLE installation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    installation_id TEXT NOT NULL,
    last_success INTEGER NOT NULL DEFAULT 0,
    auth_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    lease_owner TEXT,
    lease_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE targets (
    chat_id INTEGER PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('user', 'group')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    send_mode TEXT NOT NULL DEFAULT 'audio' CHECK (send_mode IN ('audio', 'link')),
    initialized INTEGER NOT NULL DEFAULT 0,
    initial_mode TEXT NOT NULL DEFAULT 'baseline' CHECK (initial_mode IN ('baseline', 'all')),
    history_count INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE history (
    chat_id INTEGER NOT NULL REFERENCES targets(chat_id),
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('baseline', 'pending', 'sent', 'failed')),
    delivery_mode TEXT CHECK (delivery_mode IN ('audio', 'link')),
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT,
    message_id INTEGER,
    error TEXT,
    PRIMARY KEY (chat_id, video_id)
);
-- Deliberately keep the expected count after deletion to detect lost history.
CREATE TRIGGER history_insert_count AFTER INSERT ON history BEGIN
    UPDATE targets SET history_count = history_count + 1 WHERE chat_id = NEW.chat_id;
END;
CREATE TABLE roles (
    user_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin'))
);
CREATE TABLE admin_targets (
    user_id INTEGER NOT NULL REFERENCES roles(user_id),
    chat_id INTEGER NOT NULL REFERENCES targets(chat_id),
    PRIMARY KEY (user_id, chat_id)
);
CREATE TABLE command_limits (
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    last_called INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);
CREATE TABLE webhook_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at INTEGER NOT NULL
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
