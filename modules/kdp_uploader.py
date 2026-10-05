import json
import os
import smtplib
import time
from email.mime.text import MIMEText
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger

log = logger.get()

KDP_NEW_TITLE_URL = "https://kdp.amazon.com/en_US/title-setup/paperback/new/details"
SESSION_FILE = config.SESSION_DIR / "kdp_state.json"
UPLOAD_TIMEOUT = 900_000  # 15 minutes


class SessionExpiredError(Exception):
    pass


def _send_alert(subject: str, body: str):
    try:
        gmail_user = os.environ.get("GMAIL_USER", "")
        gmail_app_pw = os.environ.get("GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_app_pw:
            log.warning("Gmail credentials not set — skipping email alert")
            return
        msg = MIMEText(body)
        msg["Subject"] = f"[KDP Bot] {subject}"
        msg["From"] = gmail_user
        msg["To"] = "yoonil.choi@gmail.com"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_app_pw)
            server.send_message(msg)
        log.info(f"Alert email sent: {subject}")
    except Exception as e:
        log.warning(f"Failed to send alert email: {e}")


def _check_login(page) -> bool:
    page.goto("https://kdp.amazon.com/en_US/dashboard", wait_until="networkidle")
    return page.locator("text=Sign in").count() == 0


def _fill_text_field(page, label_text: str, value: str):
    """Find input near a label and fill it."""
    try:
        field = page.locator(f"label:has-text('{label_text}') + div input, "
                             f"label:has-text('{label_text}') ~ div input").first
        field.fill(value)
    except Exception:
        log.warning(f"Could not fill field '{label_text}' — selector may have changed")


def run(pdf_paths: dict, metadata: dict, output_dir: Path) -> str | None:
    if not SESSION_FILE.exists():
        log.error("KDP session file not found. Run scripts/setup_kdp_session.py first.")
        _send_alert("Setup Required", "KDP session file missing. Run setup_kdp_session.py on the VM.")
        return None

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(SESSION_FILE),
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        context.set_default_timeout(UPLOAD_TIMEOUT)
        page = context.new_page()

        try:
            log.info("Checking KDP session validity")
            if not _check_login(page):
                raise SessionExpiredError("KDP session has expired")

            log.info("Navigating to new title page")
            page.goto(KDP_NEW_TITLE_URL, wait_until="networkidle")
            time.sleep(2)

            # --- Details tab ---
            log.info("Filling book details")
            _fill_text_field(page, "Book Title", metadata["title"])
            _fill_text_field(page, "Subtitle", metadata.get("subtitle", ""))
            _fill_text_field(page, "Author", metadata["author"])

            # Description (textarea)
            try:
                page.locator("textarea[name='description'], #data-print-book-description").fill(
                    metadata["description"]
                )
            except Exception:
                log.warning("Description field selector failed")

            # Keywords (7 fields)
            keywords = metadata.get("keywords", [])
            for i, kw in enumerate(keywords[:7]):
                try:
                    page.locator(f"input[name='keyword-{i}'], #keyword-{i}").fill(kw)
                except Exception:
                    log.warning(f"Keyword field {i} selector failed")

            # AI disclosure checkbox
            try:
                ai_checkbox = page.locator("input[type='checkbox'][name*='ai'], input[type='checkbox'][id*='ai']").first
                if not ai_checkbox.is_checked():
                    ai_checkbox.check()
                log.info("AI disclosure checkbox checked")
            except Exception:
                log.warning("AI disclosure checkbox not found — may need selector update")

            # Save and continue to Content tab
            try:
                page.locator("button:has-text('Save and Continue')").first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
            except Exception:
                log.warning("Save and Continue button not found")

            # --- Content tab: upload PDFs ---
            log.info("Uploading interior PDF")
            try:
                interior_input = page.locator("input[type='file'][accept*='pdf']").first
                with page.expect_file_chooser() as fc_info:
                    interior_input.click()
                file_chooser = fc_info.value
                file_chooser.set_files(str(pdf_paths["interior_pdf"]))
                page.wait_for_selector("text=Upload complete", timeout=UPLOAD_TIMEOUT)
                log.info("Interior PDF uploaded")
            except Exception as e:
                log.warning(f"Interior upload selector failed: {e}")

            log.info("Uploading cover PDF")
            try:
                cover_input = page.locator("input[type='file'][accept*='pdf']").nth(1)
                with page.expect_file_chooser() as fc_info:
                    cover_input.click()
                file_chooser = fc_info.value
                file_chooser.set_files(str(pdf_paths["cover_pdf"]))
                page.wait_for_selector("text=Upload complete", timeout=UPLOAD_TIMEOUT)
                log.info("Cover PDF uploaded")
            except Exception as e:
                log.warning(f"Cover upload selector failed: {e}")

            # Save and continue to Pricing tab
            try:
                page.locator("button:has-text('Save and Continue')").first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
            except Exception:
                log.warning("Save and Continue (content tab) button not found")

            # --- Pricing tab ---
            log.info("Setting price")
            try:
                page.locator("input[name*='price'], input[id*='price']").first.fill(
                    str(config.KDP_PRICE_USD)
                )
            except Exception:
                log.warning("Price field selector failed")

            # Publish
            try:
                page.locator("button:has-text('Publish'), button:has-text('Submit')").first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)
            except Exception:
                log.warning("Publish button not found")

            # Extract ASIN from URL or page
            asin = None
            url = page.url
            import re
            m = re.search(r"/([A-Z0-9]{10})(?:/|$)", url)
            if m:
                asin = m.group(1)
            if not asin:
                try:
                    asin_el = page.locator("text=B0").first
                    asin_text = asin_el.inner_text()
                    m2 = re.search(r"B0[A-Z0-9]{8}", asin_text)
                    if m2:
                        asin = m2.group(0)
                except Exception:
                    pass

            if asin:
                log.info(f"KDP upload successful. ASIN: {asin}")
            else:
                log.warning("Upload completed but ASIN not captured from page")
                # Save screenshot for manual verification
                screenshot_path = config.LOGS_DIR / f"kdp_post_upload_{metadata.get('niche','unknown').replace(' ','_')}.png"
                page.screenshot(path=str(screenshot_path))
                log.info(f"Screenshot saved to {screenshot_path}")

            # Save updated session
            context.storage_state(path=str(SESSION_FILE))
            return asin

        except SessionExpiredError as e:
            log.error(str(e))
            _send_alert("KDP Session Expired", "Re-run scripts/setup_kdp_session.py on the VM to refresh login.")
            return None
        except Exception as e:
            log.error(f"KDP upload failed: {e}")
            screenshot_path = config.LOGS_DIR / f"kdp_error_{int(time.time())}.png"
            try:
                page.screenshot(path=str(screenshot_path))
                log.info(f"Error screenshot: {screenshot_path}")
            except Exception:
                pass
            _send_alert("KDP Upload Failed", f"Error: {e}\nCheck logs for details.")
            return None
        finally:
            context.close()
            browser.close()
