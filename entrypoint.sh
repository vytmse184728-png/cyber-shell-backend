#!/usr/bin/env sh
set -eu

PORT="${APP_PORT:-60080}"

python - <<'PY'
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
PY

exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 run:app
