#!/usr/bin/env sh
set -eu

PORT="${APP_PORT:-60080}"

python - <<'INNER'
from app import create_app

create_app()
print('database ready')
INNER

exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 100 run:app
