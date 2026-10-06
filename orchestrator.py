#!/usr/bin/env python3
"""
Daily pipeline orchestrator.
Usage: python orchestrator.py [--dry-run] [--niche "specific niche"]
"""
import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config
from utils import logger, db
from modules import (
    niche_researcher,
    image_generator,
    pdf_assembler,
    metadata_generator,
    kdp_uploader,
    pinterest_poster,
    earnings_scraper,
)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def print_summary(run_date, niche, asin, earnings, duration_sec):
    print("\n" + "=" * 60)
    print(f"  Daily Run Summary — {run_date}")
    print("=" * 60)
    print(f"  Niche:    {niche}")
    print(f"  ASIN:     {asin or 'Not captured (check KDP dashboard)'}")
    print(f"  Duration: {duration_sec/60:.1f} minutes")
    print()
    print(f"  Today's Earnings")
    print(f"    Royalties:  ${earnings.get('royalties_usd', 0):.2f}")
    print(f"    Units Sold: {earnings.get('units_sold', 0)}")
    print(f"    KENP Reads: {earnings.get('kenp_reads', 0)}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Skip KDP upload and Pinterest posting")
    parser.add_argument("--niche", type=str, help="Override niche selection")
    parser.add_argument("--skip-images", action="store_true", help="Skip image generation (use existing)")
    args = parser.parse_args()

    log = logger.setup()
    db.init_db()

    run_date = date.today().isoformat()
    started_at = time.time()
    db.upsert_pipeline_run(run_date, started_at=run_date, status="running")

    log.info(f"=== Pipeline starting for {run_date} ===")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    config.SESSION_DIR.mkdir(parents=True, exist_ok=True)

    asin = None
    earnings = {}

    try:
        # Step 1: Niche research
        if args.niche:
            niches = [{"niche": args.niche, "seed": args.niche, "opp_score": 100.0, "asins": []}]
            niche_id = db.insert_niche(run_date, args.niche, args.niche, None, None, 100.0, selected=1)
            niches[0]["niche_id"] = niche_id
        else:
            log.info("Step 1: Niche research")
            niches = niche_researcher.run(run_date)

        niche = niches[0]
        slug = slugify(niche["niche"])
        book_dir = config.OUTPUT_DIR / run_date / slug
        book_dir.mkdir(parents=True, exist_ok=True)

        db.upsert_pipeline_run(run_date, niche_selected=niche["niche"])

        # Step 2: Image generation
        images_dir = book_dir / "images"
        if args.skip_images and images_dir.exists():
            image_paths = sorted(images_dir.glob("page_*.png"))
            log.info(f"Step 2: Skipping image generation, using {len(image_paths)} existing images")
        else:
            log.info("Step 2: Image generation")
            image_paths = image_generator.run(
                niche=niche["niche"],
                output_dir=images_dir,
                page_count=config.PAGES_PER_BOOK,
            )

        if not image_paths:
            raise RuntimeError("Image generation produced no images")

        # Step 3: Metadata generation (fast, run before PDF so title is available)
        log.info("Step 3: Metadata generation")
        book_id = db.insert_book(
            niche["niche_id"], run_date, slug,
            config.KDP_AUTHOR_PEN_NAME, len(image_paths), config.KDP_PRICE_USD
        )
        metadata = metadata_generator.run(niche=niche, output_dir=book_dir)
        metadata["book_id"] = book_id

        # Step 4: PDF assembly
        log.info("Step 4: PDF assembly")
        pdf_paths = pdf_assembler.run(
            image_paths=image_paths,
            output_dir=book_dir,
            niche=niche["niche"],
            title=metadata.get("title", ""),
            subtitle=metadata.get("subtitle", ""),
        )

        db.update_book_metadata(
            book_id,
            title=metadata.get("title"),
            subtitle=metadata.get("subtitle"),
            description=metadata.get("description"),
            keywords=metadata.get("keywords", []),
            categories=metadata.get("categories", []),
            interior_pdf=pdf_paths["interior_pdf"],
            cover_pdf=pdf_paths["cover_pdf"],
        )

        # Step 5: KDP upload
        if not args.dry_run:
            # Wait for manual approval before publishing
            approval_file = book_dir / "APPROVE_PUBLISH"
            if not approval_file.exists():
                log.info(f"Step 5: WAITING FOR PUBLISH APPROVAL — review the book then run:")
                log.info(f"  touch {approval_file}")
                log.info(f"  or use the dashboard Approve button")
                while not approval_file.exists():
                    time.sleep(30)
                log.info("Step 5: Publish approved — proceeding with KDP upload")

            log.info("Step 5: KDP upload")
            asin = kdp_uploader.run(
                pdf_paths=pdf_paths,
                metadata=metadata,
                output_dir=book_dir,
            )
            if asin:
                db.update_book_asin(book_id, asin)
                db.upsert_pipeline_run(run_date, asin_produced=asin)
        else:
            log.info("Step 5: KDP upload SKIPPED (dry-run)")

        # Step 6: Pinterest marketing
        if not args.dry_run and asin:
            log.info("Step 6: Pinterest posting")
            pin_results = pinterest_poster.run(
                asin=asin,
                metadata=metadata,
                image_paths=image_paths,
                cover_path=pdf_paths["cover_mockup"],
                book_id=book_id,
            )
            for pin in pin_results:
                if pin.get("pin_id"):
                    db.insert_pin(book_id, pin["pin_id"], pin["type"], pin["path"])
        else:
            log.info("Step 6: Pinterest SKIPPED (dry-run or no ASIN)")

        # Step 7: Earnings snapshot
        log.info("Step 7: Earnings scrape")
        earnings = earnings_scraper.run(run_date)
        db.insert_earnings(
            run_date, None, None,
            earnings.get("royalties_usd", 0),
            earnings.get("units_sold", 0),
            earnings.get("kenp_reads", 0),
            is_aggregate=1,
        )
        for book_earning in earnings.get("books", []):
            if book_earning.get("asin"):
                db.insert_earnings(
                    run_date, None, book_earning["asin"],
                    book_earning.get("royalties", 0),
                    book_earning.get("units", 0),
                    0,
                )

        duration = time.time() - started_at
        db.upsert_pipeline_run(run_date, status="success", finished_at=run_date, duration_sec=duration)
        print_summary(run_date, niche["niche"], asin, earnings, duration)

    except Exception as e:
        duration = time.time() - started_at
        log.error(f"Pipeline failed: {e}", exc_info=True)
        db.upsert_pipeline_run(run_date, status="failed", error_message=str(e), duration_sec=duration)
        sys.exit(1)


if __name__ == "__main__":
    main()
