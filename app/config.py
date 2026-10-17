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
# on the droplet in the shared secrets file every app reads
# (/etc/personal-apps/shared.env, see DEPLOYMENT.md). Import-from-
# Instagram fails with a clear 503 (not a silent no-op) if this is unset.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Used by app/distance.py (Google Distance Matrix API) to compute real
# walking/driving distances between activities - same never-committed,
# shell-set-locally / shared-secrets-file-on-the-droplet pattern as
# ANTHROPIC_API_KEY above. The distance tool fails with a clear 503 (not a
# silent no-op) if this is unset.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# social-planning (the "plans" app) - trips pulls plans from it and the two
# share Activity.plan_id links (see routers/plan_links.py). API calls go
# server-to-server on 127.0.0.1, same as finances -> trips, which sidesteps
# Cloudflare Access entirely. PLANS_PUBLIC_URL is only for links a browser
# follows back to a plan.
PLANS_API_BASE = os.environ.get("PLANS_API_BASE", "http://127.0.0.1:8020")
PLANS_PUBLIC_URL = "https://plans.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8020"
