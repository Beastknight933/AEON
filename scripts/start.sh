#!/usr/bin/env bash
# ==============================================================================
# AEON Production Startup Script for Render Free Plan & Containerized Deploys
# ==============================================================================
# On Render's Free tier, preDeployCommand is unavailable. This script runs
# pre-deployment tasks (database migrations, optional seeding) before launching
# the production Uvicorn ASGI server.
# ==============================================================================

set -e # Exit immediately on error

echo "=================================================="
echo " [AEON] Initializing backend container startup..."
echo "=================================================="

# 1. Run Alembic Database Migrations
echo " [AEON] Step 1/2: Running database migrations (alembic upgrade head)..."
if alembic upgrade head; then
    echo " [AEON] ✓ Database migrations applied successfully."
else
    echo " [AEON] ✗ Database migration failed! Aborting container startup." >&2
    exit 1
fi

# Optional Step: Seed initial database if AUTO_SEED or RUN_SEED is enabled
if [ "${AUTO_SEED}" = "true" ] || [ "${RUN_SEED}" = "true" ] || [ "${AUTO_SEED}" = "1" ]; then
    echo " [AEON] Step 1b: AUTO_SEED enabled. Running initial database seed..."
    if python scripts/seed.py; then
        echo " [AEON] ✓ Initial database seed applied successfully."
    else
        echo " [AEON] ⚠ Initial database seed finished with warnings/errors (continuing startup)." >&2
    fi
fi

# 2. Start Uvicorn Web Server
PORT="${PORT:-8000}"
echo " [AEON] Step 2/2: Starting Uvicorn server on port ${PORT}..."
echo "=================================================="

# Use exec to replace shell with Uvicorn process so OS signals (SIGTERM/SIGINT) pass directly
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
