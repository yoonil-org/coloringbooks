from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger, image_utils

log = logger.get()

# sd-cpp can load .safetensors directly — use the cached HF model file
SAFETENSORS_MODEL = Path(
    "/home/worker/.cache/huggingface/hub/models--Linaqruf--anything-v3-1"
    "/snapshots/907b769ec43b228c9943b4df5ea193d6e885f840/anything-v3-2.safetensors"
)
# GGUF path kept as fallback if user downloads one later
GGUF_MODEL = Path("/home/worker/Workspace/coloring-books/models/anything-v3-q8_0.gguf")

_sd_cpp_pipe = None
_diffusers_pipe = None


def _try_load_sdcpp():
    """Load sd-cpp with OpenCL (Intel Arc GPU). Tries GGUF first, then .safetensors."""
    global _sd_cpp_pipe
    if _sd_cpp_pipe is not None:
        return _sd_cpp_pipe

    # Prefer GGUF if available, else use safetensors from HF cache
    if GGUF_MODEL.exists():
        model_path = GGUF_MODEL
        wtype = "q8_0"
    elif SAFETENSORS_MODEL.exists():
        model_path = SAFETENSORS_MODEL
        wtype = "f16"
    else:
        log.warning("No GPU model found (GGUF or safetensors) — skipping GPU path")
        return None

    try:
        import stable_diffusion_cpp as sd
        log.info(f"Loading model via sd-cpp (OpenCL/GPU): {model_path.name}")
        pipe = sd.StableDiffusion(
            model_path=str(model_path),
            wtype=wtype,
            n_threads=-1,
            vae_decode_only=True,
        )
        _sd_cpp_pipe = pipe
        log.info(f"sd-cpp pipeline loaded on GPU (OpenCL) [{wtype}]")
        return _sd_cpp_pipe
    except Exception as e:
        log.warning(f"sd-cpp GPU load failed: {e} — falling back to CPU diffusers")
        return None


def _load_diffusers():
    """Load HuggingFace diffusers pipeline on CPU."""
    global _diffusers_pipe
    if _diffusers_pipe is not None:
        return _diffusers_pipe
    import torch
    from diffusers import StableDiffusionPipeline
    torch.set_num_threads(torch.get_num_threads())
    log.info(f"Loading diffusers model '{config.SD_MODEL_ID}' on CPU ({torch.get_num_threads()} threads)")
    pipe = StableDiffusionPipeline.from_pretrained(
        config.SD_MODEL_ID,
        torch_dtype=torch.float32,
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe = pipe.to("cpu")
    pipe.enable_attention_slicing(1)
    _diffusers_pipe = pipe
    log.info("Diffusers pipeline loaded on CPU")
    return _diffusers_pipe


PROMPT_TEMPLATE = (
    "{subject} scene, adult coloring book page, thick bold black outlines, "
    "clean line art, no shading, no gray fills, no color, pure white background, "
    "intricate details, symmetric composition, highly detailed illustration"
)

NEGATIVE_PROMPT = (
    "color, gray, shadow, shading, gradient, blur, photo, realistic, 3d render, "
    "watermark, text, signature, low quality, cropped, off-center, deformed, "
    "noise, grain, dark background, filled areas"
)


def _generate_sdcpp(pipe, prompt, seed) -> "PIL.Image.Image":
    results = pipe.generate_image(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=config.SD_WIDTH,
        height=config.SD_HEIGHT,
        sample_steps=config.SD_STEPS,
        cfg_scale=config.SD_GUIDANCE,
        seed=seed,
    )
    return results[0]


def _generate_diffusers(pipe, prompt, seed) -> "PIL.Image.Image":
    import torch
    generator = torch.Generator("cpu").manual_seed(seed)
    result = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=config.SD_WIDTH,
        height=config.SD_HEIGHT,
        num_inference_steps=config.SD_STEPS,
        guidance_scale=config.SD_GUIDANCE,
        generator=generator,
        num_images_per_prompt=1,
    )
    return result.images[0]


def run(niche: str, output_dir: Path, page_count: int = None) -> list[Path]:
    if page_count is None:
        page_count = config.PAGES_PER_BOOK

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Generating {page_count} images for niche: '{niche}'")

    sdcpp = _try_load_sdcpp()
    if sdcpp is None:
        pipe = _load_diffusers()
        backend = "cpu-diffusers"
    else:
        pipe = sdcpp
        backend = "gpu-opencl"

    log.info(f"Using backend: {backend}")
    prompt = PROMPT_TEMPLATE.format(subject=niche)
    base_seed = abs(hash(niche)) % (2**31)
    paths = []

    for i in range(page_count):
        out_path = output_dir / f"page_{i+1:03d}.png"
        if out_path.exists():
            log.debug(f"Skipping existing {out_path.name}")
            paths.append(out_path)
            continue

        log.info(f"Generating page {i+1}/{page_count} [{backend}]")
        try:
            if backend == "gpu-opencl":
                img = _generate_sdcpp(pipe, prompt, seed=base_seed + i)
            else:
                img = _generate_diffusers(pipe, prompt, seed=base_seed + i)
        except Exception as e:
            log.warning(f"Page {i+1} generation failed ({e}) — retrying")
            try:
                if backend == "gpu-opencl":
                    img = _generate_sdcpp(pipe, prompt, seed=base_seed + i + 1000)
                else:
                    img = _generate_diffusers(pipe, prompt, seed=base_seed + i + 1000)
            except Exception as e2:
                log.error(f"Page {i+1} retry also failed: {e2} — skipping")
                continue

        img = image_utils.threshold_to_bw(img)
        img = image_utils.upscale_to_kdp(img)

        if not image_utils.validate_image(img):
            log.warning(f"Page {i+1} failed validation (too dark) — keeping anyway")

        img.save(str(out_path), dpi=(config.DPI, config.DPI))
        paths.append(out_path)

    log.info(f"Image generation complete: {len(paths)}/{page_count} pages [{backend}]")
    return paths
