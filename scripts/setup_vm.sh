#!/usr/bin/env bash
# One-time VM setup. Run as the worker user.
set -e

BASE="/home/worker/Workspace/coloring-books"
VENV="$BASE/.venv"

echo "=== Step 1: Add worker to render and video groups ==="
sudo usermod -aG render,video worker
echo "Groups updated. You must log out and back in for this to take effect."

echo "=== Step 2: Install system packages ==="
sudo apt-get update -q
sudo apt-get install -y python3-pip curl git lxml libxml2-dev libxslt-dev \
  fonts-dejavu-core fonts-liberation

echo "=== Step 3: Install uv ==="
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

echo "=== Step 4: Create Python 3.13 venv ==="
uv python install 3.13
uv venv --python 3.13 "$VENV"

echo "=== Step 5: Install Python dependencies ==="
"$VENV/bin/pip" install --upgrade pip

# Core torch + IPEX for Intel Arc
"$VENV/bin/pip" install torch==2.8.0 \
  --index-url https://download.pytorch.org/whl/cpu

"$VENV/bin/pip" install intel_extension_for_pytorch==2.8.10+xpu \
  --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/ \
  || echo "IPEX install failed — will fall back to CPU"

# Diffusers + other deps
"$VENV/bin/pip" install \
  diffusers==0.31.0 \
  transformers==4.47.0 \
  accelerate==1.2.1 \
  Pillow==12.1.1 \
  fpdf2==2.8.2 \
  requests==2.32.5 \
  "beautifulsoup4==4.12.3" \
  lxml==5.3.0 \
  anthropic==0.40.0 \
  playwright==1.49.0 \
  python-dotenv==1.0.1

echo "=== Step 6: Install Playwright browsers ==="
"$VENV/bin/playwright" install chromium
"$VENV/bin/playwright" install-deps chromium

echo "=== Step 7: Download SD model ==="
"$VENV/bin/python" "$BASE/scripts/install_sd_model.py"

echo "=== Step 8: Install VM crontab ==="
(crontab -l 2>/dev/null; echo "0 2 * * * $VENV/bin/python $BASE/orchestrator.py >> $BASE/logs/cron.log 2>&1") | crontab -
echo "Cron job installed: runs daily at 02:00 UTC"

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Log out and back in (for render/video group to take effect)"
echo "  2. Copy your .env file to $BASE/.env"
echo "  3. Run: $VENV/bin/python $BASE/scripts/setup_kdp_session.py"
echo "  4. Test: $VENV/bin/python $BASE/orchestrator.py --dry-run"
