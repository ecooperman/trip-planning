import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import SHARED_ASSETS_BASE
from .routers import activities, categories, distance, dog_care, instagram_import, stays, travel, trips

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.


def _get_git_sha() -> str:
    """Short commit hash the running app was deployed from, read straight
    from the repo on disk (the deploy pulls a real git checkout) - no CI
    wiring needed, and it can never drift from what's actually running.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


GIT_SHA = _get_git_sha()

app = FastAPI(title="Trip Planning")
templates = Jinja2Templates(directory="templates")


@app.get("/api/version")
def get_version():
    return {"version": GIT_SHA}


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so these take priority over it.
def _render(name: str):
    def handler(request: Request):
        return templates.TemplateResponse(request, name, {"shared_assets_base": SHARED_ASSETS_BASE})

    return handler


app.get("/", response_class=HTMLResponse)(_render("index.html"))
app.get("/activities.html", response_class=HTMLResponse)(_render("activities.html"))
app.get("/trip.html", response_class=HTMLResponse)(_render("trip.html"))
app.get("/agenda.html", response_class=HTMLResponse)(_render("agenda.html"))


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Never let the browser (or iOS's aggressive standalone-PWA cache) serve
    a stale copy of the app - this is a single-user local tool, not a public
    site, so there's no real cost to always fetching fresh. Same fix as
    time-management's app/main.py; `no-cache` on just the static files
    (an earlier attempt here) wasn't strong enough - a CDN/PWA cache layer
    isn't obligated to revalidate the way `no-cache` asks, only `no-store`
    is an unambiguous "never cache this, anywhere" signal.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(trips.router)
app.include_router(activities.router)
app.include_router(stays.router)
app.include_router(travel.router)
app.include_router(dog_care.router)
app.include_router(categories.router)
app.include_router(instagram_import.router)
app.include_router(distance.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
