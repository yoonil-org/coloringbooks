from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger, image_utils

log = logger.get()

SDXL_MODEL = Path("/home/worker/Workspace/coloring-books/models/sd_xl_base_1.0.safetensors")
LORA_DIR   = Path("/home/worker/Workspace/coloring-books/models/loras")

# LoRA filenames and their weights
LORAS = [
    ("ColoringBookRedmond-ColoringBook-ColoringBookAF.safetensors", 0.9),
    ("LineAniRedmondV2-Lineart-LineAniAF.safetensors", 0.7),
]

_sd_cpp_pipe = None


def _try_load_sdcpp():
    global _sd_cpp_pipe
    if _sd_cpp_pipe is not None:
        return _sd_cpp_pipe

    if not SDXL_MODEL.exists():
        log.warning(f"SDXL model not found at {SDXL_MODEL} — cannot generate")
        return None

    try:
        import stable_diffusion_cpp as sd
        # Intel Arc OpenCL driver cannot compile GEGLU/SwiGLU kernels used by SDXL.
        # offload_params_to_cpu=True keeps UNet in CPU RAM and avoids GPU kernel compile.
        log.info(f"Loading SDXL model via sd-cpp (CPU offload): {SDXL_MODEL.name}")
        pipe = sd.StableDiffusion(
            model_path=str(SDXL_MODEL),
            wtype="f16",
            n_threads=-1,
            vae_decode_only=True,
            offload_params_to_cpu=True,
        )
        _sd_cpp_pipe = pipe
        log.info("SDXL sd-cpp pipeline loaded [f16, CPU-offload]")
        return _sd_cpp_pipe
    except Exception as e:
        log.warning(f"sd-cpp SDXL load failed: {e}")
        return None


# SDXL trigger words: ColoringBookAF activates ColoringBookRedmond, LineAniAF activates LineAni
PROMPT_TEMPLATE = (
    "children's coloring book page, cute {subject}, "
    "thick bold black outlines, large open white areas to color, "
    "simple clean line art, pure white background, cartoon style, "
    "friendly cute design, minimal detail, no shading, no fills"
)

NEGATIVE_PROMPT = (
    "color, colours, gray, grey, shadow, shading, gradient, blur, smudge, "
    "photo, realistic, 3d render, watermark, text, signature, logo, url, "
    "copyright, website, low quality, cropped, deformed, noise, grain, "
    "dark background, black background, filled areas, solid black areas, messy lines, "
    "intricate, complex, adult coloring book, sketch marks, anime"
)


def _build_lora_prompt(base_prompt: str) -> str:
    return base_prompt


def _generate_sdcpp(pipe, prompt, seed) -> "PIL.Image.Image":
    full_prompt = _build_lora_prompt(prompt)
    results = pipe.generate_image(
        prompt=full_prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=config.SD_WIDTH,
        height=config.SD_HEIGHT,
        sample_steps=config.SD_STEPS,
        cfg_scale=config.SD_GUIDANCE,
        sample_method=getattr(config, "SD_SAMPLER", "euler_a"),
        seed=seed,
    )
    return results[0]


def run(niche: str, output_dir: Path, page_count: int = None) -> list[Path]:
    if page_count is None:
        page_count = config.PAGES_PER_BOOK

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Generating {page_count} images for niche: '{niche}'")

    pipe = _try_load_sdcpp()
    if pipe is None:
        log.error("SDXL model not available — cannot generate images")
        return []

    log.info("Using backend: cpu-offload (SDXL)")
    prompt = PROMPT_TEMPLATE.format(subject=niche)
    base_seed = abs(hash(niche)) % (2**31)
    paths = []

    for i in range(page_count):
        out_path = output_dir / f"page_{i+1:03d}.png"
        if out_path.exists():
            log.debug(f"Skipping existing {out_path.name}")
            paths.append(out_path)
            continue

        log.info(f"Generating page {i+1}/{page_count} [cpu-offload SDXL]")
        try:
            img = _generate_sdcpp(pipe, prompt, seed=base_seed + i)
        except Exception as e:
            log.warning(f"Page {i+1} generation failed ({e}) — retrying")
            try:
                img = _generate_sdcpp(pipe, prompt, seed=base_seed + i + 1000)
            except Exception as e2:
                log.error(f"Page {i+1} retry also failed: {e2} — skipping")
                continue

        img = image_utils.threshold_to_bw(img)
        img = image_utils.upscale_to_kdp(img)

        if not image_utils.validate_image(img):
            log.warning(f"Page {i+1} failed validation (too dark) — keeping anyway")

        img.save(str(out_path), dpi=(config.DPI, config.DPI))
        paths.append(out_path)

    log.info(f"Image generation complete: {len(paths)}/{page_count} pages [SDXL]")
    return paths
