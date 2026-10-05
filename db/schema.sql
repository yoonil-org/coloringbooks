PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS niches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,
    niche       TEXT NOT NULL,
    seed        TEXT NOT NULL,
    bsr_median  REAL,
    avg_reviews REAL,
    opp_score   REAL NOT NULL,
    selected    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS books (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    niche_id        INTEGER NOT NULL REFERENCES niches(id),
    run_date        TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    title           TEXT,
    subtitle        TEXT,
    author          TEXT,
    description     TEXT,
    keywords        TEXT,
    categories      TEXT,
    asin            TEXT,
    kdp_status      TEXT DEFAULT 'pending',
    interior_pdf    TEXT,
    cover_pdf       TEXT,
    page_count      INTEGER,
    price_usd       REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    uploaded_at     TEXT,
    live_at         TEXT
);

CREATE TABLE IF NOT EXISTS earnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scrape_date     TEXT NOT NULL,
    book_id         INTEGER REFERENCES books(id),
    asin            TEXT,
    royalties_usd   REAL NOT NULL DEFAULT 0.0,
    units_sold      INTEGER NOT NULL DEFAULT 0,
    kenp_reads      INTEGER NOT NULL DEFAULT 0,
    is_aggregate    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(scrape_date, asin)
);

CREATE TABLE IF NOT EXISTS pinterest_pins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id),
    pin_id      TEXT,
    pin_type    TEXT,
    image_path  TEXT,
    posted_at   TEXT DEFAULT (datetime('now')),
    status      TEXT DEFAULT 'posted'
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date        TEXT NOT NULL UNIQUE,
    started_at      TEXT,
    finished_at     TEXT,
    status          TEXT DEFAULT 'running',
    niche_selected  TEXT,
    asin_produced   TEXT,
    error_message   TEXT,
    duration_sec    REAL
);

CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings(scrape_date);
CREATE INDEX IF NOT EXISTS idx_books_asin ON books(asin);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(kdp_status);
