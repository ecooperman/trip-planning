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

# Used by app/stay_extraction.py to read lodging listings into candidate
# stays. Never committed - set directly in the local shell for dev, and on
# the droplet in the shared secrets file every app reads
# (/etc/personal-apps/shared.env, see DEPLOYMENT.md). The stay importer
# fails with a clear 503 (not a silent no-op) if this is unset.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Used by app/distance.py (Google Distance Matrix API) to compute real
# walking/driving distances between activities - same never-committed,
# shell-set-locally / shared-secrets-file-on-the-droplet pattern as
# ANTHROPIC_API_KEY above. The distance tool fails with a clear 503 (not a
# silent no-op) if this is unset.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# Optional: a Jina Reader (r.jina.ai) key for the stay importer's fallback on
# pages that come back thin. Like the two above it is the HOUSE key, used only
# for administrators; everyone else brings their own (see app/apikeys.py).
JINA_API_KEY = os.environ.get("JINA_API_KEY")

# social-planning (the "plans" app) - trips pulls plans from it and the two
# share Activity.plan_id links (see routers/plan_links.py). API calls go
# server-to-server on 127.0.0.1, same as finances -> trips, which sidesteps
# Cloudflare Access entirely. PLANS_PUBLIC_URL is only for links a browser
# follows back to a plan.
PLANS_API_BASE = os.environ.get("PLANS_API_BASE", "http://127.0.0.1:8020")
PLANS_PUBLIC_URL = "https://plans.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8020"

# --- who is signed in (see app/auth.py) -------------------------------------
# Cloudflare Access authenticates everyone before a request reaches the app, and
# shared_python.auth verifies the signed token it attaches. CF_TEAM_DOMAIN and
# CF_ACCESS_AUD come from the shared secrets file (see shared_python/settings.py
# and DEPLOYMENT.md), not from here.

# Locally there's no Cloudflare in front, so requests are treated as coming
# from this address; a Cf-Access-Authenticated-User-Email header or a
# `dev_user` cookie plays someone else. Never used in production.
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev@localhost.test").strip().lower()

# Administrators (comma-separated): the only people who get the features that
# are really the app owner's own - dog care, the social-planning link. The
# lists that existed before accounts also go to whoever signs in first as one
# of them (or, unset in production, to whoever signs in first at all). Locally
# it includes DEV_USER_EMAIL.
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
ADOPT_LEGACY_ANY = not ADMIN_EMAILS and ENV == "production"
if ENV != "production":
    ADMIN_EMAILS.add(DEV_USER_EMAIL)

# Other apps on this machine (finances reads trip costs, social-planning sends
# plans over) call this one directly on 127.0.0.1 with no signed-in person.
# They prove who they are with this shared secret (header X-Service-Token, same
# value in every app's environment - put it in /etc/personal-apps/shared.env)
# and act as SERVICE_USER_EMAIL, by default the first administrator. Unset, the
# feature is off and those calls are refused.
SERVICE_TOKEN = os.environ.get("TRIPS_SERVICE_TOKEN") or None
SERVICE_USER_EMAIL = (os.environ.get("SERVICE_USER_EMAIL") or "").strip().lower() or None


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --- letting new people in (see app/routers/invites.py) ----------------------
# A trip's owner can ask for someone who has no account yet to be let in; an
# administrator approves each request, which adds the email to the Cloudflare
# Access group that lets people through the login gate. These settings live in
# the shared secrets file (/etc/personal-apps/shared.env, see DEPLOYMENT.md).
#
# How many people each person may ask for (administrators are unlimited). Every
# request counts unless the person cancels it while it's still waiting.
INVITES_PER_USER = _int_env("INVITES_PER_USER", 5)

# --- links in what we send (see app/notify.py) ------------------------------
# The Cloudflare group, ntfy/Pushover and email settings are shared by every app
# (shared_python/settings.py); only where this app lives is its own.
PUBLIC_URL = "https://trips.evancooperman.com" if ENV == "production" else f"http://127.0.0.1:{PORT}"

# --- people's own API keys (see app/apikeys.py) -----------------------------
# Keys the person saves on their Profile page are encrypted with
# KEY_ENCRYPTION_SECRET, which lives in the shared secrets file with the other
# shared settings (shared_python/settings.py, DEPLOYMENT.md) - never change it once
# keys are saved.
