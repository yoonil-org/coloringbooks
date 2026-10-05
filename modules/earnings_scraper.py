import json
import re
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger

log = logger.get()

SESSION_FILE = config.SESSION_DIR / "kdp_reports_state.json"
KDP_REPORTS_URL = "https://kdpreports.amazon.com/"


def _parse_currency(text: str) -> float:
    m = re.search(r"[\$£€]?\s*([\d,]+\.?\d*)", text.replace(",", ""))
    if m:
        return float(m.group(1))
    return 0.0


def _parse_int(text: str) -> int:
    m = re.search(r"([\d,]+)", text.replace(",", ""))
    if m:
        return int(m.group(1))
    return 0


def run(run_date: str) -> dict:
    log.info("Scraping KDP Reports earnings")

    # Use publishing session as fallback if reports session missing
    session_file = SESSION_FILE if SESSION_FILE.exists() else (config.SESSION_DIR / "kdp_state.json")
    if not session_file.exists():
        log.warning("No KDP session available for earnings scrape")
        return {"royalties_usd": 0.0, "units_sold": 0, "kenp_reads": 0, "books": []}

    from playwright.sync_api import sync_playwright

    results = {"royalties_usd": 0.0, "units_sold": 0, "kenp_reads": 0, "books": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(session_file),
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        context.set_default_timeout(60_000)
        page = context.new_page()

        try:
            page.goto(KDP_REPORTS_URL, wait_until="networkidle")
            time.sleep(3)

            # Check if logged in
            if page.locator("text=Sign in").count() > 0:
                log.warning("KDP Reports session expired — earnings will be 0 for today")
                return results

            # Scrape summary cards
            try:
                royalty_el = page.locator("[data-testid='royalties-amount'], .royalties-value, text=$").first
                results["royalties_usd"] = _parse_currency(royalty_el.inner_text())
            except Exception:
                pass

            try:
                units_el = page.locator("[data-testid='units-sold'], .units-value").first
                results["units_sold"] = _parse_int(units_el.inner_text())
            except Exception:
                pass

            try:
                kenp_el = page.locator("[data-testid='kenp-reads'], .kenp-value").first
                results["kenp_reads"] = _parse_int(kenp_el.inner_text())
            except Exception:
                pass

            # Try to get per-book breakdown from table
            try:
                rows = page.locator("table tr, .book-row").all()
                for row in rows[1:]:  # skip header
                    cells = row.locator("td").all()
                    if len(cells) >= 3:
                        book_data = {
                            "title": cells[0].inner_text().strip() if cells else "",
                            "asin": "",
                            "units": _parse_int(cells[1].inner_text()) if len(cells) > 1 else 0,
                            "royalties": _parse_currency(cells[2].inner_text()) if len(cells) > 2 else 0.0,
                        }
                        # Try to extract ASIN from row link
                        link = row.locator("a[href*='/dp/']").first
                        if link.count() > 0:
                            href = link.get_attribute("href")
                            m = re.search(r"/dp/([A-Z0-9]{10})", href or "")
                            if m:
                                book_data["asin"] = m.group(1)
                        results["books"].append(book_data)
            except Exception as e:
                log.debug(f"Per-book table scrape failed: {e}")

            # Save earnings to file
            out_path = config.DATA_DIR / f"earnings_{run_date}.json"
            out_path.write_text(json.dumps(results, indent=2))
            log.info(
                f"Earnings scraped: ${results['royalties_usd']:.2f} royalties, "
                f"{results['units_sold']} units, {results['kenp_reads']} KENP reads"
            )

            # Save updated session
            context.storage_state(path=str(session_file))

        except Exception as e:
            log.error(f"Earnings scrape failed: {e}")
        finally:
            context.close()
            browser.close()

    return results
