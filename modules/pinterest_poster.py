import base64
import json
import os
import time
from pathlib import Path
import requests
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger

log = logger.get()

PINTEREST_API = "https://api.pinterest.com/v5"


def _headers() -> dict:
    token = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _check_token():
    resp = requests.get(f"{PINTEREST_API}/user_account", headers=_headers(), timeout=10)
    if resp.status_code == 401:
        log.error("Pinterest token is invalid or expired")
        return False
    if resp.status_code == 200:
        data = resp.json()
        log.info(f"Pinterest account: {data.get('username', 'unknown')}")
        return True
    log.warning(f"Pinterest token check returned {resp.status_code}")
    return True


def _get_board_id() -> str | None:
    board_id = os.environ.get("PINTEREST_BOARD_ID", "")
    if board_id:
        return board_id
    # Auto-fetch first board
    resp = requests.get(f"{PINTEREST_API}/boards", headers=_headers(), timeout=10)
    if resp.status_code == 200:
        boards = resp.json().get("items", [])
        if boards:
            bid = boards[0]["id"]
            log.info(f"Using Pinterest board: {boards[0]['name']} ({bid})")
            return bid
    log.error("No Pinterest board found and PINTEREST_BOARD_ID not set")
    return None


def _post_pin(board_id: str, title: str, description: str, link: str, image_path: Path) -> str | None:
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:500],
        "link": link,
        "media_source": {
            "source_type": "image_base64",
            "content_type": "image/png",
            "data": img_b64,
        },
    }

    resp = requests.post(f"{PINTEREST_API}/pins", headers=_headers(), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        pin_id = resp.json().get("id", "")
        log.info(f"Pinterest pin posted: {pin_id} — '{title[:50]}'")
        return pin_id
    else:
        log.error(f"Pinterest pin failed: {resp.status_code} — {resp.text[:200]}")
        return None


def run(asin: str, metadata: dict, image_paths: list[Path], cover_path: Path, book_id: int) -> list[dict]:
    log.info(f"Posting Pinterest pins for ASIN {asin}")

    if not _check_token():
        return []

    board_id = _get_board_id()
    if not board_id:
        return []

    amazon_url = f"https://www.amazon.com/dp/{asin}"
    title = metadata.get("title", metadata.get("niche", "Coloring Book"))
    keywords = metadata.get("keywords", [])
    kw_str = " ".join(f"#{k.replace(' ', '')}" for k in keywords[:4])

    pin_dir = cover_path.parent

    # Pin 1: Cover mockup
    pin_results = []
    desc1 = (
        f"{title} — perfect for relaxation and stress relief. "
        f"30 intricate coloring pages for adults. {kw_str} #coloringbook #adultcoloring"
    )
    time.sleep(2)
    pid1 = _post_pin(board_id, title, desc1, amazon_url, cover_path)
    pin_results.append({"type": "cover", "pin_id": pid1, "path": str(cover_path)})

    # Pin 2: Interior page showcase (page 3)
    if len(image_paths) > 2:
        interior_pin_path = pin_dir / "pinterest_pin.png"
        if interior_pin_path.exists():
            time.sleep(2)
            desc2 = (
                f"Peek inside: {title}. Each page features hand-crafted intricate designs. "
                f"Ideal for mindfulness and creative meditation. {kw_str} #coloringtherapy"
            )
            pid2 = _post_pin(board_id, f"Inside Look: {title}", desc2, amazon_url, interior_pin_path)
            pin_results.append({"type": "interior", "pin_id": pid2, "path": str(interior_pin_path)})

    # Pin 3: Single page close-up
    if len(image_paths) > 10:
        time.sleep(2)
        page_path = image_paths[10]
        desc3 = (
            f"One of 30 beautiful pages from {title}. "
            f"Download and start coloring today! Link in bio. {kw_str} #coloringpage"
        )
        pid3 = _post_pin(board_id, f"Coloring Page: {title}", desc3, amazon_url, page_path)
        pin_results.append({"type": "page_closeup", "pin_id": pid3, "path": str(page_path)})

    log.info(f"Pinterest posting complete: {len([r for r in pin_results if r['pin_id']])} pins posted")
    return pin_results
