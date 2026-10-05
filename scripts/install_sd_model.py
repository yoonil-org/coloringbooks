#!/usr/bin/env python3
"""Pre-downloads the SD model to the HuggingFace cache."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

print(f"Downloading model: {config.SD_MODEL_ID}")
print("This will download ~4.3GB. Please wait...")

from huggingface_hub import snapshot_download
snapshot_download(config.SD_MODEL_ID)
print("Model download complete.")
