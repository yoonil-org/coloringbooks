import sqlite3
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    schema = (Path(__file__).parent.parent / "db" / "schema.sql").read_text()
    with get_connection() as conn:
        conn.executescript(schema)


def insert_niche(run_date, niche, seed, bsr_median, avg_reviews, opp_score, selected=0) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO niches (run_date,niche,seed,bsr_median,avg_reviews,opp_score,selected) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_date, niche, seed, bsr_median, avg_reviews, opp_score, selected),
        )
        return cur.lastrowid


def insert_book(niche_id, run_date, slug, author, page_count, price_usd) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO books (niche_id,run_date,slug,author,page_count,price_usd) "
            "VALUES (?,?,?,?,?,?)",
            (niche_id, run_date, slug, author, page_count, price_usd),
        )
        return cur.lastrowid


def update_book_metadata(book_id, title, subtitle, description, keywords, categories, interior_pdf, cover_pdf):
    with get_connection() as conn:
        conn.execute(
            "UPDATE books SET title=?,subtitle=?,description=?,keywords=?,categories=?,"
            "interior_pdf=?,cover_pdf=? WHERE id=?",
            (title, subtitle, description,
             json.dumps(keywords), json.dumps(categories),
             str(interior_pdf), str(cover_pdf), book_id),
        )


def update_book_asin(book_id, asin):
    with get_connection() as conn:
        conn.execute(
            "UPDATE books SET asin=?,kdp_status='uploaded',uploaded_at=datetime('now') WHERE id=?",
            (asin, book_id),
        )


def insert_earnings(scrape_date, book_id, asin, royalties_usd, units_sold, kenp_reads, is_aggregate=0):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO earnings "
            "(scrape_date,book_id,asin,royalties_usd,units_sold,kenp_reads,is_aggregate) "
            "VALUES (?,?,?,?,?,?,?)",
            (scrape_date, book_id, asin, royalties_usd, units_sold, kenp_reads, is_aggregate),
        )


def insert_pin(book_id, pin_id, pin_type, image_path, status="posted"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO pinterest_pins (book_id,pin_id,pin_type,image_path,status) VALUES (?,?,?,?,?)",
            (book_id, pin_id, pin_type, str(image_path), status),
        )


def upsert_pipeline_run(run_date, **kwargs):
    cols = ", ".join(kwargs.keys())
    placeholders = ", ".join("?" for _ in kwargs)
    updates = ", ".join(f"{k}=?" for k in kwargs)
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO pipeline_runs (run_date,{cols}) VALUES (?,{placeholders}) "
            f"ON CONFLICT(run_date) DO UPDATE SET {updates}",
            (run_date, *kwargs.values(), *kwargs.values()),
        )


def get_books_with_asin():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM books WHERE asin IS NOT NULL").fetchall()


def get_daily_earnings_summary(date_str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT SUM(royalties_usd) as total_royalties, SUM(units_sold) as total_units "
            "FROM earnings WHERE scrape_date=? AND is_aggregate=0",
            (date_str,),
        ).fetchone()
