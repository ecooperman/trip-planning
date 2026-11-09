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
# There is no login form: Cloudflare Access authenticates everyone before a
# request reaches the app and attaches a signed token saying who it was. In
# production the app verifies that token and REFUSES every request unless both
# values below are set (from Zero Trust -> Access -> Applications -> (the app)
# -> Overview; several tags may be comma-separated). They live in the shared
# secrets file every app reads (/etc/personal-apps/shared.env, see
# DEPLOYMENT.md), never in this repo.
CF_TEAM_DOMAIN = os.environ.get("CF_TEAM_DOMAIN")  # e.g. "yourteam.cloudflareaccess.com"
CF_ACCESS_AUD = os.environ.get("CF_ACCESS_AUD")

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

# The Cloudflare API token needs only "Access: Organizations, Identity
# Providers, and Groups Write". The group is the one the shared-apps Access
# policy allows (the "Invitees" group). Without these, approving a request
# works locally (the Cloudflare step is skipped) but is refused in production.
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_INVITEES_GROUP_ID = os.environ.get("CF_INVITEES_GROUP_ID")
# Cloudflare's free Access plan allows 50 people; approving past this is refused.
ACCESS_SEAT_CAP = _int_env("ACCESS_SEAT_CAP", 50)

# --- telling the administrator a request is waiting (see app/notify.py) -----
# Each channel is on when its settings are present; use any combination.
PUBLIC_URL = "https://trips.evancooperman.com" if ENV == "production" else f"http://127.0.0.1:{PORT}"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")  # anyone who knows the topic can read it: make it long and random
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN")  # only for a protected topic
PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = _int_env("SMTP_PORT", 587)  # 465 = SSL from the start, anything else = STARTTLS
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")  # where the email goes

# --- people's own API keys (see app/apikeys.py) -----------------------------
# Anthropic, Google Maps and Jina keys the person saves on their Profile page
# are stored encrypted with this secret, so a copy of the database file (a
# backup, a download for inspection) holds nothing usable. Any long random
# string will do; generate one with:
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Put it in the shared secrets file (/etc/personal-apps/shared.env) and never
# change it afterwards - saved keys can't be read back with a different one, and
# people would have to enter theirs again. Without it, production refuses to
# save keys (locally a fixed development secret is used).
KEY_ENCRYPTION_SECRET = os.environ.get("KEY_ENCRYPTION_SECRET")

