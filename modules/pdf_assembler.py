from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger, image_utils
from PIL import Image

log = logger.get()


def _make_interior_pdf(image_paths: list[Path], out_path: Path):
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="in", format=(config.PAGE_W_IN, config.PAGE_H_IN))
    pdf.set_auto_page_break(False)
    pdf.set_compression(False)

    for img_path in image_paths:
        pdf.add_page()
        pdf.image(str(img_path), x=0, y=0, w=config.PAGE_W_IN, h=config.PAGE_H_IN)

    pdf.output(str(out_path))
    size_mb = out_path.stat().st_size / 1024 / 1024
    log.info(f"Interior PDF: {out_path.name} ({size_mb:.1f} MB, {len(image_paths)} pages)")
    return out_path


def _make_cover_pdf(cover_img: Image.Image, out_path: Path, page_count: int):
    from fpdf import FPDF

    # KDP cover width = back cover + spine + front cover + bleed
    spine_w = 0.002252 * page_count
    total_w = 8.5 + spine_w + 8.5 + 0.125  # add 0.125" bleed
    total_h = 11.25  # 11" + 0.125" top/bottom bleed

    # Resize cover image to match these exact dimensions at 300 DPI
    cover_px_w = int(total_w * config.DPI)
    cover_px_h = int(total_h * config.DPI)
    cover_resized = cover_img.convert("RGB").resize((cover_px_w, cover_px_h), Image.LANCZOS)

    tmp_path = out_path.parent / "_cover_tmp.jpg"
    cover_resized.save(str(tmp_path), format="JPEG", quality=100, dpi=(config.DPI, config.DPI))

    pdf = FPDF(orientation="L", unit="in", format=(total_w, total_h))
    pdf.set_auto_page_break(False)
    pdf.set_compression(False)
    pdf.add_page()
    pdf.image(str(tmp_path), x=0, y=0, w=total_w, h=total_h)
    pdf.output(str(out_path))

    tmp_path.unlink(missing_ok=True)
    size_mb = out_path.stat().st_size / 1024 / 1024
    log.info(f"Cover PDF: {out_path.name} ({size_mb:.1f} MB)")
    return out_path


def run(image_paths: list[Path], output_dir: Path, niche: str, title: str = "", subtitle: str = "") -> dict:
    log.info(f"Assembling PDFs for '{niche}' ({len(image_paths)} pages)")

    interior_path = output_dir / "interior.pdf"
    cover_path = output_dir / "cover.pdf"
    cover_mockup_path = output_dir / "cover_mockup.png"
    pin_path = output_dir / "pinterest_pin.png"

    _make_interior_pdf(image_paths, interior_path)

    # Build cover using first interior page
    first_page = Image.open(str(image_paths[0])).convert("RGB")
    cover_img = image_utils.make_cover_image(
        first_page,
        title or niche.title(),
        subtitle or "An Adult Coloring Book",
    )
    cover_img.save(str(cover_mockup_path), dpi=(config.DPI, config.DPI))
    _make_cover_pdf(cover_img, cover_path, len(image_paths))

    # Pinterest pin: cover mockup + one interior page
    second_page = Image.open(str(image_paths[min(5, len(image_paths) - 1)])).convert("RGB")
    pin_img = image_utils.make_pinterest_pin(cover_img, second_page, title or niche.title())
    pin_img.save(str(pin_path))
    log.info(f"Pinterest pin saved: {pin_path.name}")

    assert interior_path.stat().st_size > 10_000 * len(image_paths), "Interior PDF suspiciously small"
    assert cover_path.stat().st_size > 50_000, "Cover PDF suspiciously small"

    return {
        "interior_pdf": interior_path,
        "cover_pdf": cover_path,
        "cover_mockup": cover_mockup_path,
        "pin_image": pin_path,
    }
