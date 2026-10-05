from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import config


def threshold_to_bw(img: Image.Image, threshold: int = 128) -> Image.Image:
    """Convert to B&W. Auto-inverts if background is dark (SD sometimes generates inverted images)."""
    import numpy as np
    gray = img.convert("L")
    arr = np.array(gray)
    # Sample corners to detect background color
    h, w = arr.shape
    corners = [arr[0,0], arr[0,w-1], arr[h-1,0], arr[h-1,w-1]]
    bg = sum(corners) / 4
    if bg < 128:
        # Dark background — invert before thresholding
        gray = Image.fromarray(255 - arr)
    return gray.point(lambda p: 255 if p >= threshold else 0, "L")


def upscale_to_kdp(img: Image.Image) -> Image.Image:
    target_w = int(config.PAGE_W_IN * config.DPI)  # 2550
    target_h = int(config.PAGE_H_IN * config.DPI)  # 3300
    resized = img.resize((target_w, target_h), Image.LANCZOS)
    resized.info["dpi"] = (config.DPI, config.DPI)
    return resized


def validate_image(img: Image.Image) -> bool:
    expected_w = int(config.PAGE_W_IN * config.DPI)
    expected_h = int(config.PAGE_H_IN * config.DPI)
    if img.size != (expected_w, expected_h):
        return False
    import numpy as np
    arr = np.array(img.convert("L"))
    mean = arr.mean()
    return float(mean) > 100  # mostly white (0=black, 255=white)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_pinterest_pin(cover_img: Image.Image, interior_img: Image.Image, title: str) -> Image.Image:
    pin = Image.new("RGB", (config.PIN_W_PX, config.PIN_H_PX), "white")

    cover_h = int(config.PIN_H_PX * 0.65)
    cover_resized = cover_img.resize((config.PIN_W_PX, cover_h), Image.LANCZOS)
    pin.paste(cover_resized, (0, 0))

    strip_h = int(config.PIN_H_PX * 0.25)
    strip_y = cover_h
    interior_resized = interior_img.resize((config.PIN_W_PX, strip_h), Image.LANCZOS)
    pin.paste(interior_resized, (0, strip_y))

    bar_y = cover_h + strip_h
    bar_h = config.PIN_H_PX - bar_y
    draw = ImageDraw.Draw(pin)
    draw.rectangle([(0, bar_y), (config.PIN_W_PX, config.PIN_H_PX)], fill="#1a1a2e")
    font = _load_font(36)
    text_bbox = draw.textbbox((0, 0), title, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_x = (config.PIN_W_PX - text_w) // 2
    text_y = bar_y + (bar_h - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), title, fill="white", font=font)

    return pin


def make_cover_image(interior_img: Image.Image, title: str, subtitle: str) -> Image.Image:
    cover = Image.new("RGB", (config.KDP_COVER_W_PX, config.KDP_COVER_H_PX), "#1a1a2e")

    page_h = int(config.KDP_COVER_H_PX * 0.85)
    page_w = int(page_h * (config.PAGE_W_IN / config.PAGE_H_IN))
    page_resized = interior_img.convert("RGB").resize((page_w, page_h), Image.LANCZOS)
    page_x = config.KDP_COVER_W_PX - page_w - 60
    page_y = (config.KDP_COVER_H_PX - page_h) // 2
    cover.paste(page_resized, (page_x, page_y))

    draw = ImageDraw.Draw(cover)
    title_font = _load_font(80)
    sub_font = _load_font(42)
    label_font = _load_font(34)

    draw.text((80, 200), title, fill="white", font=title_font)
    draw.text((80, 320), subtitle, fill="#cccccc", font=sub_font)
    draw.text((80, config.KDP_COVER_H_PX - 120), "An Adult Coloring Book", fill="#aaaaaa", font=label_font)

    return cover
