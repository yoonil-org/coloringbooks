#!/usr/bin/env python3
"""Quick earnings report from the local database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import db

db.init_db()

with db.get_connection() as conn:
    # All-time summary
    totals = conn.execute(
        "SELECT SUM(royalties_usd) as total, SUM(units_sold) as units "
        "FROM earnings WHERE is_aggregate=0"
    ).fetchone()
    print(f"\n{'='*50}")
    print(f"  All-Time Earnings")
    print(f"{'='*50}")
    print(f"  Total Royalties: ${totals['total'] or 0:.2f}")
    print(f"  Total Units:     {totals['units'] or 0}")

    # Last 7 days
    recent = conn.execute(
        "SELECT scrape_date, SUM(royalties_usd) as daily_royalties, SUM(units_sold) as daily_units "
        "FROM earnings WHERE is_aggregate=1 "
        "ORDER BY scrape_date DESC LIMIT 7"
    ).fetchall()
    print(f"\n  Last 7 Days")
    print(f"  {'Date':<12} {'Royalties':>12} {'Units':>8}")
    print(f"  {'-'*35}")
    for row in recent:
        print(f"  {row['scrape_date']:<12} ${row['daily_royalties'] or 0:>10.2f} {row['daily_units'] or 0:>8}")

    # Books catalog
    books = conn.execute(
        "SELECT title, asin, kdp_status, created_at FROM books ORDER BY created_at DESC"
    ).fetchall()
    print(f"\n  Catalog ({len(books)} books)")
    print(f"  {'Title':<45} {'ASIN':<12} {'Status'}")
    print(f"  {'-'*70}")
    for b in books:
        title = (b['title'] or 'Untitled')[:44]
        print(f"  {title:<45} {b['asin'] or 'pending':<12} {b['kdp_status']}")
    print()
