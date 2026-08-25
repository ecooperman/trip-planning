import os

HOST = "127.0.0.1"
PORT = 8060

# "local" (default, for `uvicorn app.main:app --reload` on a dev machine) or
# "production" (set once, droplet-wide, via systemd's DefaultEnvironment -
# see DEPLOYMENT.md - so every app inherits it with no per-service config).
# Drives which shared-assets host the app's templates point at, so
# switching between local iteration and the real deploy never means
# hand-editing a URL and remembering to revert it.
ENV = os.environ.get("APP_ENV", "local")
SHARED_ASSETS_BASE = "https://static.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8070"

# Used by app/ai_extraction.py to turn an Instagram caption into candidate
# activities. Never committed - set directly in the local shell for dev, and
# on the droplet via `sudo systemctl edit trip-planning` (same pattern as
# resume-admin's INTERNAL_API_TOKEN, see DEPLOYMENT.md). Import-from-
# Instagram fails with a clear 503 (not a silent no-op) if this is unset.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Used by app/distance.py (Google Distance Matrix API) to compute real
# walking/driving distances between activities - same never-committed,
# shell-set-locally / systemd-set-on-the-droplet pattern as
# ANTHROPIC_API_KEY above. The distance tool fails with a clear 503 (not a
# silent no-op) if this is unset.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
