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
