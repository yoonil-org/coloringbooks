import json
import random
import re
import time
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger, db

log = logger.get()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


def _headers() -> dict:
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    }


def _is_captcha(html: str) -> bool:
    return any(s in html.lower() for s in ["robot check", "automated access", "captcha", "verify you're human"])


def _parse_bsr(product_page_html: str) -> float | None:
    soup = BeautifulSoup(product_page_html, "lxml")
    for li in soup.select("li.zg_hrsr_item, #SalesRank, #detailBulletsWrapper_feature_div li"):
        text = li.get_text()
        if "best seller" in text.lower() or "rank" in text.lower():
            m = re.search(r"#([\d,]+)", text)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def _parse_reviews(card_html) -> float:
    text = card_html.get_text()
    m = re.search(r"([\d,]+)\s+rating", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", ""))
    return 999.0


def _fetch(session: requests.Session, url: str) -> str | None:
    try:
        resp = session.get(url, headers=_headers(), timeout=15)
        if resp.status_code == 200:
            return resp.text
        log.warning(f"HTTP {resp.status_code} for {url}")
        return None
    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return None


def _research_seed(session: requests.Session, seed: str, captcha_count: list) -> dict | None:
    if captcha_count[0] >= config.CAPTCHA_ABORT_THRESHOLD:
        return None

    url = f"{config.AMAZON_SEARCH_BASE}?k={seed.replace(' ', '+')}+coloring+book&i=stripbooks&rh=n%3A283155"
    log.info(f"Researching seed: {seed}")
    html = _fetch(session, url)
    if not html:
        return None
    if _is_captcha(html):
        captcha_count[0] += 1
        log.warning(f"CAPTCHA hit for seed '{seed}' (count={captcha_count[0]})")
        return None

    soup = BeautifulSoup(html, "lxml")
    cards = soup.select('[data-component-type="s-search-result"]')[:10]
    if not cards:
        log.warning(f"No results for seed: {seed}")
        return None

    reviews = [_parse_reviews(c) for c in cards]
    avg_reviews = sum(reviews) / len(reviews)

    # Fetch BSR from top 3 product pages
    asins = [c.get("data-asin") for c in cards[:3] if c.get("data-asin")]
    bsr_values = []
    for asin in asins:
        time.sleep(random.uniform(config.SCRAPE_DELAY_MIN, config.SCRAPE_DELAY_MAX))
        pdp_html = _fetch(session, f"https://www.amazon.com/dp/{asin}")
        if pdp_html and not _is_captcha(pdp_html):
            bsr = _parse_bsr(pdp_html)
            if bsr:
                bsr_values.append(bsr)
        elif pdp_html and _is_captcha(pdp_html):
            captcha_count[0] += 1

    bsr_median = sorted(bsr_values)[len(bsr_values) // 2] if bsr_values else 999_999

    score = max(0.0, 100.0 - (bsr_median / 1000) - (avg_reviews * 2))

    return {
        "niche": seed,
        "seed": seed,
        "bsr_median": bsr_median,
        "avg_reviews": avg_reviews,
        "opp_score": round(score, 2),
        "asins": asins,
    }


def run(run_date: str) -> list[dict]:
    log.info("=== Niche Research starting ===")
    seeds_path = config.DATA_DIR / "seed_niches.json"
    seeds: list[str] = json.loads(seeds_path.read_text())
    random.shuffle(seeds)
    seeds = seeds[: config.MAX_SEEDS_PER_RUN]

    session = requests.Session()
    captcha_count = [0]
    results = []

    for seed in seeds:
        if captcha_count[0] >= config.CAPTCHA_ABORT_THRESHOLD:
            log.warning("CAPTCHA threshold reached — aborting niche research early")
            break
        result = _research_seed(session, seed, captcha_count)
        if result:
            results.append(result)
        time.sleep(random.uniform(config.SCRAPE_DELAY_MIN, config.SCRAPE_DELAY_MAX))

    if not results:
        log.warning("No niche results from scraping — using random seed fallback")
        seed = random.choice(seeds)
        results = [{"niche": seed, "seed": seed, "bsr_median": None, "avg_reviews": None, "opp_score": 50.0, "asins": []}]

    results.sort(key=lambda r: r["opp_score"], reverse=True)

    for i, r in enumerate(results):
        niche_id = db.insert_niche(
            run_date, r["niche"], r["seed"],
            r.get("bsr_median"), r.get("avg_reviews"), r["opp_score"],
            selected=1 if i == 0 else 0,
        )
        r["niche_id"] = niche_id

    out_dir = config.OUTPUT_DIR / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ranked_niches.json").write_text(json.dumps(results, indent=2))
    log.info(f"Top niche: '{results[0]['niche']}' (score={results[0]['opp_score']})")
    return results
