#!/usr/bin/env bash
set -euxo pipefail
exec gunicorn \
    --workers 2 \
    --max-requests 2000 \
    --timeout 30 \
    --log-level debug \
    --bind :8000 \
    ws.wsgi
