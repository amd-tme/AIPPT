-- Outline2PPT Slide Catalog Schema
-- SQLite database for cataloging, tagging, and versioning slides

CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    slide_count INTEGER NOT NULL DEFAULT 0,
    cataloged_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    author TEXT NOT NULL DEFAULT '',
    created_date TEXT DEFAULT NULL,
    modified_date TEXT DEFAULT NULL,
    subject TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source_script_path TEXT DEFAULT NULL,
    source_engine TEXT DEFAULT NULL,
    source_theme TEXT DEFAULT NULL,
    outline_path TEXT DEFAULT NULL,
    source_generated_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS slides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    author TEXT NOT NULL DEFAULT '',
    slide_created_date TEXT DEFAULT NULL,
    layout_type TEXT DEFAULT NULL,
    image_content_hash TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK(source IN ('ai', 'taxonomy', 'manual'))
);

CREATE TABLE IF NOT EXISTS slide_tags (
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (slide_id, tag_id)
);

CREATE TABLE IF NOT EXISTS taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT ''
);

-- Named sections within a deck
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(deck_id, name),
    UNIQUE(deck_id, position)
);

-- Each slide belongs to at most one section
CREATE TABLE IF NOT EXISTS slide_sections (
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    PRIMARY KEY (slide_id)
);

-- Append-only edit history for tracking field changes.
-- slide_id is nullable: script-file patches (field='script') are not tied to a
-- single slide row, so they record NULL here.
CREATE TABLE IF NOT EXISTS edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slide_id INTEGER REFERENCES slides(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT 'web',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_edit_history_slide ON edit_history(slide_id);

-- Chat conversations scoped to a deck (or a specific slide within it)
CREATE TABLE IF NOT EXISTS chat_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    scope TEXT NOT NULL DEFAULT 'deck' CHECK(scope IN ('deck', 'slide')),
    model TEXT NOT NULL DEFAULT '',
    script_path TEXT DEFAULT NULL,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_conv_deck ON chat_conversations(deck_id);

-- Messages within a chat conversation
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    slide_id INTEGER REFERENCES slides(id) ON DELETE SET NULL,
    mode TEXT DEFAULT 'ask' CHECK(mode IN ('ask', 'edit', 'review') OR mode IS NULL),
    patch_json TEXT DEFAULT NULL,
    patch_applied_at TEXT DEFAULT NULL,
    patch_reverted_at TEXT DEFAULT NULL,
    edit_history_id INTEGER DEFAULT NULL,  -- edit_history row for this message's applied patch
    tokens_in INTEGER DEFAULT NULL,
    tokens_out INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_msg_conv ON chat_messages(conversation_id);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_decks_file_path ON decks(file_path);
CREATE INDEX IF NOT EXISTS idx_decks_file_hash ON decks(file_hash);
CREATE INDEX IF NOT EXISTS idx_slides_deck ON slides(deck_id);
CREATE INDEX IF NOT EXISTS idx_slides_hash ON slides(content_hash);
CREATE INDEX IF NOT EXISTS idx_slides_title ON slides(title);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_sections_deck ON sections(deck_id);
CREATE INDEX IF NOT EXISTS idx_slide_sections_section ON slide_sections(section_id);
