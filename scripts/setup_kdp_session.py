#!/usr/bin/env python3
"""
Interactive script to create the KDP Playwright session.
Run this once on the VM to log in to KDP and save the session.

Usage:
  python scripts/setup_kdp_session.py
  python scripts/setup_kdp_session.py --reports  # for KDP Reports session
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

parser = argparse.ArgumentParser()
parser.add_argument("--reports", action="store_true", help="Set up KDP Reports session instead")
args = parser.parse_args()

config.SESSION_DIR.mkdir(parents=True, exist_ok=True)

if args.reports:
    url = "https://kdpreports.amazon.com/"
    session_file = config.SESSION_DIR / "kdp_reports_state.json"
    label = "KDP Reports"
else:
    url = "https://kdp.amazon.com/en_US/dashboard"
    session_file = config.SESSION_DIR / "kdp_state.json"
    label = "KDP"

print(f"\nSetting up {label} session.")
print("A browser window will open. Log in to your Amazon/KDP account.")
print("After logging in successfully, come back here and press Enter.\n")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # headless=False to allow manual login
    browser = p.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/Los_Angeles",
    )
    page = context.new_page()
    page.goto(url)

    print("Browser opened. Complete the login in the browser window.")
    print("Press Enter here once you are logged in and see the dashboard...")
    input()

    context.storage_state(path=str(session_file))
    print(f"\nSession saved to: {session_file}")
    print(f"File size: {session_file.stat().st_size} bytes")

    browser.close()

print(f"\n{label} session setup complete!")
