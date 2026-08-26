"""SQLite schema, migrations, and helpers."""

from __future__ import annotations

import sqlite3

from pagefolio.config import DB_PATH, ROOT

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  title             TEXT NOT NULL,
  subtitle          TEXT,
  author            TEXT,
  translator        TEXT,
  isbn              TEXT,
  asin              TEXT,
  cover_url         TEXT,
  local_cover_path  TEXT,
  publisher         TEXT,
  language          TEXT,
  notes             TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_isbn  ON books(isbn);

CREATE TABLE IF NOT EXISTS reading_months (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL
              REFERENCES books(id) ON DELETE CASCADE,
  year        INTEGER NOT NULL,
  month       INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
  finished_on TEXT,
  notes       TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reading_months_year_month
  ON reading_months(year, month);
CREATE INDEX IF NOT EXISTS idx_reading_months_book_id
  ON reading_months(book_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def book_to_dict(row: sqlite3.Row) -> dict:
    local = row["local_cover_path"]
    has_cover = bool(local) and (ROOT / local).exists()
    return {
        "id": row["id"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "author": row["author"],
        "translator": row["translator"],
        "isbn": row["isbn"],
        "asin": row["asin"],
        "cover_url": row["cover_url"],
        "local_cover_path": local if has_cover else None,
        "publisher": row["publisher"],
        "language": row["language"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _book_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(books)")}


def _migrate_books_bibliographic_fields(conn: sqlite3.Connection) -> None:
    cols = _book_columns(conn)
    if "subtitle" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN subtitle TEXT")
    if "translator" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN translator TEXT")


def _migrate_books_cover_column(conn: sqlite3.Connection) -> None:
    cols = _book_columns(conn)
    if "local_cover_path" in cols:
        return
    if "cover_path" in cols:
        conn.execute("ALTER TABLE books RENAME COLUMN cover_path TO local_cover_path")
        return
    conn.execute("ALTER TABLE books ADD COLUMN local_cover_path TEXT")


def _has_reading_months_unique(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('table', 'index') "
        "AND tbl_name = 'reading_months' AND sql IS NOT NULL"
    ).fetchall()
    return any(
        "UNIQUE" in (sql or "").upper() and "BOOK_ID" in (sql or "").upper()
        for (sql,) in rows
    )


def _migrate_drop_reading_months_unique(conn: sqlite3.Connection) -> None:
    if not _has_reading_months_unique(conn):
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TABLE reading_months_new (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          book_id     INTEGER NOT NULL
                      REFERENCES books(id) ON DELETE CASCADE,
          year        INTEGER NOT NULL,
          month       INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
          finished_on TEXT,
          notes       TEXT,
          created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO reading_months_new
          (id, book_id, year, month, finished_on, notes, created_at)
        SELECT id, book_id, year, month, finished_on, notes, created_at
        FROM reading_months;
        DROP TABLE reading_months;
        ALTER TABLE reading_months_new RENAME TO reading_months;
        CREATE INDEX IF NOT EXISTS idx_reading_months_year_month
          ON reading_months(year, month);
        CREATE INDEX IF NOT EXISTS idx_reading_months_book_id
          ON reading_months(book_id);
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def init_db() -> str:
    existed = DB_PATH.exists()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        _migrate_books_cover_column(conn)
        _migrate_books_bibliographic_fields(conn)
        _migrate_drop_reading_months_unique(conn)
        conn.commit()
    status = "already present" if existed else "created"
    return f"reading.db {status} at {DB_PATH}"
