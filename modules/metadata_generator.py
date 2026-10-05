import json
import re
from pathlib import Path
import requests
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from utils import logger

log = logger.get()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"

SYSTEM_PROMPT = """You are a professional Amazon KDP publishing consultant specializing in adult coloring books.
Your metadata generates books that rank well organically on Amazon search.
Always return ONLY a valid JSON object — no markdown fences, no explanation, just the raw JSON."""

def _call_ollama(niche: dict) -> dict:
    prompt = f"""{SYSTEM_PROMPT}

Generate KDP metadata for a 30-page adult coloring book.

Niche: {niche['niche']}
Target audience: adults seeking stress relief, relaxation, creative activity
Author pen name: {config.KDP_AUTHOR_PEN_NAME}
Price: ${config.KDP_PRICE_USD}

Return ONLY a valid JSON object with these exact keys:
{{
  "title": "string (max 200 chars, compelling, includes niche keywords)",
  "subtitle": "string (max 200 chars, e.g. '30 Relaxing Designs for Stress Relief and Mindfulness')",
  "author": "{config.KDP_AUTHOR_PEN_NAME}",
  "description": "string (150-300 words, opens with hook, mentions relaxation benefits, ends with CTA, discloses AI-assisted illustrations)",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6", "keyword7"],
  "categories": ["{config.KDP_CATEGORY_1}", "{config.KDP_CATEGORY_2}"],
  "ai_disclosure": true
}}

Keywords must be: high-search-volume Amazon terms, max 50 chars each, exactly 7 items, specific to the niche.
Return raw JSON only, no code fences."""

    resp = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }, timeout=120)
    resp.raise_for_status()

    raw = resp.json()["response"].strip()
    # Strip markdown fences if model adds them anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw.strip())
    # Extract JSON object if there's surrounding text
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    return json.loads(raw)


def _fallback_metadata(niche: dict) -> dict:
    name = niche["niche"].title()
    return {
        "title": f"{name} Coloring Book for Adults",
        "subtitle": "30 Relaxing Designs for Stress Relief and Mindfulness",
        "author": config.KDP_AUTHOR_PEN_NAME,
        "description": (
            f"Discover the joy of coloring with this {niche['niche']} themed adult coloring book. "
            "Each of the 30 pages features intricate designs crafted to help you unwind and express "
            "your creativity. Perfect for stress relief, mindfulness, and relaxation. "
            "Illustrations were created with AI assistance. Grab your colored pencils and start today!"
        ),
        "keywords": [
            f"{niche['niche']} coloring book",
            "adult coloring book stress relief",
            "coloring book for adults relaxation",
            f"{niche['niche']} gifts for women",
            "mindfulness coloring pages",
            "stress relief activity book",
            "creative coloring pages adults",
        ],
        "categories": [config.KDP_CATEGORY_1, config.KDP_CATEGORY_2],
        "ai_disclosure": True,
    }


def run(niche: dict, output_dir: Path) -> dict:
    log.info(f"Generating metadata for niche: '{niche['niche']}' via Ollama ({OLLAMA_MODEL})")

    out_path = output_dir / "metadata.json"
    if out_path.exists():
        log.info("Metadata already exists, loading from disk")
        return json.loads(out_path.read_text())

    for attempt in range(2):
        try:
            metadata = _call_ollama(niche)
            # Validate required keys
            for key in ("title", "subtitle", "author", "description", "keywords", "categories"):
                assert key in metadata, f"Missing key: {key}"
            assert isinstance(metadata["keywords"], list) and len(metadata["keywords"]) == 7
            log.info(f"Metadata generated: '{metadata['title']}'")
            break
        except Exception as e:
            if attempt == 0:
                log.warning(f"Metadata attempt 1 failed: {e} — retrying")
            else:
                log.error(f"Metadata generation failed after 2 attempts: {e} — using fallback")
                metadata = _fallback_metadata(niche)

    metadata["niche"] = niche["niche"]
    metadata["niche_id"] = niche.get("niche_id")
    out_path.write_text(json.dumps(metadata, indent=2))
    return metadata
