from pathlib import Path

BASE_DIR = Path("/home/worker/Workspace/coloring-books")
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SESSION_DIR = BASE_DIR / "playwright_sessions"
DB_PATH = DATA_DIR / "coloring_books.db"

# SD model
SD_MODEL_ID = "Linaqruf/anything-v3-1"
SD_DEVICE = "xpu"  # falls back to cpu in image_generator if xpu unavailable
SD_WIDTH = 1024
SD_HEIGHT = 1024
SD_STEPS = 30
SD_GUIDANCE = 7.5

# Book specs
PAGES_PER_BOOK = 30
PAGE_W_IN = 8.5
PAGE_H_IN = 11.0
DPI = 300
KDP_COVER_W_PX = 2560
KDP_COVER_H_PX = 1600
PIN_W_PX = 1000
PIN_H_PX = 1500

# KDP publishing
KDP_PRICE_USD = 7.99
KDP_AUTHOR_PEN_NAME = "Willow Lane Press"
KDP_CATEGORY_1 = "Crafts, Hobbies & Home"
KDP_CATEGORY_2 = "Arts & Photography"

# Amazon scraping
AMAZON_SEARCH_BASE = "https://www.amazon.com/s"
SCRAPE_DELAY_MIN = 3.0
SCRAPE_DELAY_MAX = 8.0
MAX_SEEDS_PER_RUN = 8
CAPTCHA_ABORT_THRESHOLD = 2

# Niche scoring
BSR_GOOD = 50_000
BSR_OK = 100_000
REVIEWS_LOW = 30
REVIEWS_OK = 50
