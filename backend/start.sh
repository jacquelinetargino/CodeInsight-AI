#!/bin/sh
# Usado pelo Render (Docker Command: "sh start.sh"): aplica as migrations e sobe a API.
# O Render injeta PORT; localmente cai para 8000.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
