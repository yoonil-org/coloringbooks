#!/usr/bin/env bash
# Start the KDP Coloring Books admin dashboard on port 8082.
# Usage: ./dashboard/run.sh [--reload]
#
# Access via SSH port forwarding:
#   ssh -i ~/.ssh/id_ed25519_cp_vm -L 8082:localhost:8082 worker@100.64.1.1 -N &
# Then open: http://localhost:8082

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate venv
source "$PROJECT_DIR/.venv/bin/activate"

# Ensure dependencies are present
python - <<'PYCHECK'
missing = []
for pkg in ('fastapi', 'uvicorn', 'jinja2', 'multipart', 'requests'):
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    import sys, subprocess
    print(f'[run.sh] Installing missing packages: {missing}', flush=True)
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q',
                           'fastapi', 'uvicorn[standard]', 'jinja2', 'python-multipart', 'requests'])
PYCHECK

cd "$PROJECT_DIR"

EXTRA_ARGS=()
if [[ "${1:-}" == '--reload' ]]; then
  EXTRA_ARGS=('--reload')
fi

echo '[run.sh] Starting dashboard on http://0.0.0.0:8082'
echo '[run.sh] SSH tunnel: ssh -i ~/.ssh/id_ed25519_cp_vm -L 8082:localhost:8082 worker@100.64.1.1 -N &'
exec uvicorn dashboard.app:app     --host 0.0.0.0     --port 8082     --log-level info     "${EXTRA_ARGS[@]}"
