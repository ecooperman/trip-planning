# Trip Planning

Plan trips with lodging (stays) and activities. Create one or more trips,
add activities and stays to each, or create activities standalone and
attach them to a trip later. Stays validate that a trip's date range is
fully covered by lodging, and activity/stay URLs can pull in a title,
description, and image via Open Graph tags (Instagram, Facebook, Airbnb,
VRBO, or any other page that exposes them).

## Run it

```bash
cd trip-planning
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

Then open http://127.0.0.1:8060 (host/port are set in `app/config.py`).

The SQLite database (`trips.db`) is not created by the app itself -
`alembic upgrade head` creates it. This only needs to be run once for a
fresh install; see below for how schema changes are handled from here on.

## API-first design

The backend (`app/`) is a plain JSON REST API (`/docs` for the interactive
Swagger UI) with no knowledge of the frontend. The frontend (`static/`) is a
thin vanilla-JS client with no build step, talking to the API over `fetch`.
That separation means the backend can be tested and used entirely on its
own, and the frontend can later be swapped for something richer without
touching the API.

**Trips** (`app/routers/trips.py`)
- `GET/POST /api/trips`, `GET/PATCH/DELETE /api/trips/{id}`
  (`DELETE` takes `?delete_activities=true` to also delete its activities
  instead of just unlinking them; its stays are always deleted with it)
- `GET /api/trips/{id}/activities`, `GET /api/trips/{id}/stays`
- `GET /api/trips/{id}/stay-coverage` - whether every day of the trip is
  covered by a non-archived stay
- `GET /api/trips/cost-summary` - per non-archived trip, the summed cost of
  its non-archived activities + booked stays (cents). Read by the
  **finances** app to forecast trip spend; not used by this app's own UI.
- `POST/DELETE /api/trips/{id}/activities/{activity_id}` - associate/unlink
  an existing activity

**Activities** (`app/routers/activities.py`) - independent of any trip;
`trip_id` on create auto-associates
- `GET /api/activities` (`?trip_id=`, `?unassociated=true`), `POST /api/activities`
- `GET/PATCH/DELETE /api/activities/{id}`
- `POST /api/activities/{id}/scrape` - fetch OG-tag preview from `url`

**Stays** (`app/routers/stays.py`) - always belong to exactly one trip
(`trip_id` required on create); marking one `booked` on a trip archives the
others on that trip
- `POST /api/stays`, `GET/PATCH/DELETE /api/stays/{id}`
- `POST /api/stays/{id}/scrape`

## Accounts and sharing

There is no sign-in form. Cloudflare Access authenticates everyone before a
request reaches the app and tells it who it was, so the app just reads that
email (`app/auth.py`). Passing the gate is not enough to use the app, though:
Cloudflare's allowed group is shared with the other apps, so each app decides
for itself who is **enabled**. A person has a row in `users` with `status`
`active` (enabled) or `removed`; anyone with no row, or a removed one, gets a 403
explaining that (and the HTML pages show a plain "no access" page with a Log out
link instead of an empty app). Accounts are only created by the administrator's
decision: approving an invite, or adding the person on the Users page. The
administrators in `ADMIN_EMAILS` always get one on first sight (and, before
`ADMIN_EMAILS` is set in production, the first person in does, taking over the
pre-accounts data); so does the service user that other apps call in as. `GET
/api/me` says who you are (and whether you're the administrator).

- **Users page** (`/users.html`, administrator only; `GET/POST /api/admin/users`,
  `POST .../{id}/revoke`, `POST .../{id}/restore`, `DELETE .../{id}`): everyone with
  an account and what they own. *Add someone* lets them through the Cloudflare gate,
  gives them an account and emails them (adding a removed person restores them).
  *Remove access* sets `removed` here only - it never touches Cloudflare, because
  another app may still want them - and deletes nothing, so *Restore* puts it all
  back. *Delete account data* is a separate step, offered only for someone already
  removed: it erases the trips they own (for everyone they were shared with, with
  their activities, stays and the rest), their other activities, places and
  categories, saved API keys, their place on other people's trips and the requests
  they made, behind a confirmation that spells out the counts. The email row stays,
  removed, so signing in again can't hand them a fresh account. Administrators can't
  be removed or deleted.

- **Everything is yours unless shared.** Trips, activities, places and
  categories each belong to the person who created them; a stranger's ids are a
  404, never a 403.
- **Sharing a trip** (owner: the **Share** button on the trip page or inside the trip's
  card on the trips list, which also shows a "people" or "View only" badge - or `GET/POST
  /api/trips/{id}/members`, `PATCH/DELETE .../members/{user_id}`): by email, as
  `edit` or `view`. The page's panel is `access.js` from shared-assets, the same
  one the lists app uses. Only someone who can use the app *right now* can be added:
  they need an active account here, and Cloudflare is asked (read-only) that they
  are still in the Invitees group (or an administrator). Being in the group for
  another app isn't enough. Anyone else is a 404 ("That person can't sign in
  yet"), which the page turns into an offer to **request an invite**; someone the
  administrator removed is a 409 saying only the administrator can restore them.
  - **owner** (creator, exactly one): everything, plus sharing, archiving and
    deleting the trip. Anyone else can leave a trip shared with them.
  - **edit**: works with the trip's content - its activities, stays, travel,
    comparison criteria, dates and name.
  - **view**: reads all of that, and can export it.
- **Inviting people who can't sign in yet** works exactly as in the lists app
  (see its README): an owner asks (`POST /api/trips/{id}/invites`, up to
  `INVITES_PER_USER` different people, default 5, administrators unlimited and
  auto-approved); the administrator approves or declines on `/invites.html`
  (nav link with a waiting count; `GET /api/admin/invites`, `POST .../{id}/approve`
  and `/decline`). Approval adds the email to the Cloudflare Invitees group
  (`shared_python.cloudflare` (the shared-python package), refused in production if `CF_API_TOKEN`, `CF_ACCOUNT_ID`
  and `CF_INVITEES_GROUP_ID` aren't set; `ACCESS_SEAT_CAP`, default 50) and puts
  them on the trip, then **emails them** (`app/notify.py`, which calls `shared_python.notify`; needs `SMTP_HOST` +
  `SMTP_FROM`). The administrator is told of each request by ntfy, Pushover and/or
  email (`NTFY_TOPIC`, `PUSHOVER_*`, `NOTIFY_EMAIL`). All of these settings are the
  ones the lists app already uses, in `/etc/personal-apps/shared.env`. The quota and
  the queue are per app (this app's `invites` table), so an approval here doesn't
  use up lists invites - but anyone approved in either app is in the one shared
  Cloudflare group, so can then be added directly to trips in both.
- **Inviting someone to the app itself** (no trip shared): the Invites page is for everyone, with the shared-assets
  `app-invites.js` panel (`GET/POST /api/app-invites`, `DELETE /api/app-invites/{id}`). Same allowance, approval and Cloudflare
  step as a trip invite; approving only lets the person in with an empty account and emails them how to sign in. Stored as an
  `invites` row with `for_app` set and no trip; one per email. The administrator also sees every **declined** request (to the app or to one trip) on the Invites page, with **Allow again**
  (`GET /api/admin/invites/declined`, `POST /api/admin/invites/{id}/reinstate`): it removes the declined request so anyone may ask for
  that person again, and the original asker gets that invite back.
- **What sharing shares.** A trip's activities belong to the *trip owner's*
  library, even ones an editor adds: an activity on a trip is always its
  owner's, so an editor's activity can't be moved onto the owner's trip (or the
  owner's onto theirs) - the library rule is enforced when linking. An editor can
  pick the owner's places and categories for those activities, but only the
  owner edits places, categories and photos; others see a place only through an
  activity on a trip shared with them. Unlinking an activity returns it to the
  owner's library, out of the editor's sight.
- **The pages only offer what your role allows** (`applyTripRole` in `static/common.js`
  puts `role-view` / `role-edit` / `role-owner` on `<body>`; `style.css` hides what
  a role can't use). A view-only member sees the trip, stays, travel, activities,
  agenda and comparison with no Edit, Add, Delete, Archive or Share, no tap-to-create
  or drag on the agenda, and read-only inputs on the comparison; an editor sees all
  of that except what only the owner may do (archive, delete, share, create a place
  from an activity). Mark a new owner-only control `needs-owner` and an
  editor-and-up control `needs-edit`. This is presentation only: the server refuses
  everything regardless, and `tests/test_viewer_changes_nothing.py` calls every write
  route as a view-only member to prove it.
- **Paid services use each person's own keys** (`app/apikeys.py`, the Profile page at
  `/profile.html`, reached from the email in the page header). Stay import and the
  screenshot reader need an Anthropic key, the distance tool a Google Maps key (Distance
  Matrix API enabled), and Jina is an optional extra for pages that block fetching.
  A call uses the person's own saved key; failing that the server's key from the
  environment (`ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`, `JINA_API_KEY`) **only if they
  are an administrator**; anyone else without a key simply doesn't have the feature, and
  the page says how to turn it on. So there's no cost to meter for other people. Keys
  are checked with the service when saved (a refused one isn't kept), stored encrypted
  with `KEY_ENCRYPTION_SECRET` (production refuses to save keys without it; never change
  it, or saved keys become unreadable and people must re-enter them), never sent back to
  the browser, and never logged. Cached distance answers need no key. `GET /api/me`
  reports `can_use` per service so pages show a notice in place of a feature that would fail.
- **Dog care and the plans link are the administrator's alone** (the emails in
  `ADMIN_EMAILS`): the server refuses them to everyone else, even on a shared
  trip, and the pages don't show them.
- **Other apps calling this one** (finances reads `GET /api/trips/cost-summary`,
  social-planning sends plans to `POST /api/plan-links/import`) have no signed-in
  person, so they send a shared secret as `X-Service-Token`
  (`TRIPS_SERVICE_TOKEN`, the same value in each app's environment - put it in
  `/etc/personal-apps/shared.env`) and act as the administrator. Only the
  endpoints meant for them accept it; a wrong token is refused outright.
- **Fetching URLs people type in is guarded** (`app/netguard.py`): http(s) only,
  the host must resolve only to public addresses, redirects are checked hop by
  hop and the body is size-capped, so no one can steer the server at its own
  network. Paid API quotas are not built yet.
- **Existing data:** the migration parks everything on a placeholder user and
  the first administrator to sign in takes it over (set `ADMIN_EMAILS` to
  restrict that to specific emails - do it before inviting anyone).
- **Production sign-in check:** `CF_TEAM_DOMAIN` and `CF_ACCESS_AUD` are
  required (see the root `DEPLOYMENT.md`); the app answers 503 to everything
  without them and never trusts the plain email header.
- **Local development:** every request is `DEV_USER_EMAIL` (default
  `dev@localhost.test`); to be someone else send a
  `Cf-Access-Authenticated-User-Email` header or run
  `document.cookie = "dev_user=bob@example.com; path=/"` in the browser
  console (delete the cookie to go back).

Tests (`pytest`, after `pip install -r requirements-dev.txt`) run the real
migrations on a throwaway database and check every endpoint against the access
rules, plus sign-in tokens and the URL guard.

## Schema changes (Alembic)

Schema is owned by migrations under `migrations/versions/`, not by wiping
`trips.db`. To change the schema:

```bash
# 1. Edit app/models.py as usual
# 2. Generate a migration from the diff
alembic revision --autogenerate -m "short description"
# 3. Look over the generated file in migrations/versions/ - autogenerate
#    is good but not infallible (e.g. it won't detect a plain column rename
#    on its own)
# 4. Apply it
alembic upgrade head
```

This preserves existing data. Useful commands: `alembic current` (what
revision the db is at), `alembic check` (does the db match `models.py`
right now), `alembic downgrade -1` (undo the last migration).

SQLite can't `ALTER TABLE` to add a constraint directly, so
`migrations/env.py` has `render_as_batch=True` set, which makes autogenerate
wrap those changes in `op.batch_alter_table(...)` (SQLite rebuilds the table
under the hood). If autogenerate produces a `batch_op.create_foreign_key(None,
...)` / `drop_constraint(None, ...)` call, give it an explicit name in both
`upgrade()` and `downgrade()` - SQLite's batch mode needs a name to
reference, and will fail with `ValueError: Constraint must have a name`
otherwise.

## Upgrading to Postgres later

Everything goes through SQLAlchemy + Alembic, so moving off SQLite is mostly
a matter of swapping `DATABASE_URL` in `app/database.py` (and
`sqlalchemy.url` in `alembic.ini`) for a Postgres connection string,
installing a driver (`psycopg`), and running `alembic upgrade head` against
the new database - no application code depends on SQLite specifics.

## Deploying

Runs as a systemd service on the Digital Ocean droplet, reached through a
Cloudflare Tunnel (no inbound ports opened on the droplet) and gated by
Cloudflare Access - see `deploy/trip-planning.service`.

One-time setup on the droplet:

```bash
sudo mkdir -p /opt/apps/trip-planning && sudo chown deploy:deploy /opt/apps/trip-planning
# as the deploy user:
git clone <this repo's SSH URL> /opt/apps/trip-planning
cd /opt/apps/trip-planning
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo cp deploy/trip-planning.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trip-planning
```

Then add an ingress entry for `127.0.0.1:8060` to `/etc/cloudflared/config.yml`,
route DNS for its hostname (`cloudflared tunnel route dns <tunnel-name>
<hostname>`), and add a Cloudflare Access policy for that hostname.

Ongoing deploys are automatic: `.github/workflows/deploy.yml` runs on every
push to `main` - it SSHes in, pulls, reinstalls dependencies, runs `alembic
upgrade head`, and restarts the service. Needs these repo secrets set once
(Settings -> Secrets and variables -> Actions): `DO_HOST`, `DO_USER` (the
`deploy` user), `DO_SSH_KEY` (that user's private key).

## Notes

- `app/scraping/` is the same Open-Graph-tag strategy pattern used in
  social-planning's `ideas` scraper, extended with Airbnb and VRBO
  strategies plus a generic fallback that matches any URL - so unrecognized
  sites still get an OG-tag preview if they expose one. Add another
  site-specific strategy (hotels.com, Expedia, Kayak, ...) by copying
  `app/scraping/airbnb.py` and registering it in `app/scraping/registry.py`.
- A scraped page's picture is kept, not hot-linked: Instagram-style signed image addresses
  stop working after a few weeks, so `app/imagecache.py` downloads the image when a scrape is
  saved (through `netguard`, images only, never SVG) into the `cached_images` table and the
  activity/place/stay stores `/api/cached-images/<id>` instead. If the download fails the
  original address is stored, and the pages hide an image that no longer loads.
- The frontend has no build step: `static/common.js` holds fetch/DOM
  helpers shared by every page, and `static/activity-shared.js` holds the
  activity form/card used identically by `activities.html` (standalone) and
  `trip.html` (scoped to a trip via `tripId`) - the only difference between
  the two is whether a newly-created activity gets auto-associated.
- An activity's trip association is modeled as a many-to-many join table
  (`trip_activities`) even though the API only lets an activity belong to
  one trip today (see `crud.associate_activity`) - so allowing an activity
  on multiple trips later doesn't need a migration, just a small crud
  change. A stay's `trip_id` is a plain required foreign key instead, since
  a stay has no meaning outside its trip.

## To do

The running to-do list for all projects is `../TODO.md` (in the personal-projects
folder, one level up; not in git).
