import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud
from .auth import NO_ACCESS, is_admin, signed_in_email
from .config import SHARED_ASSETS_BASE
from .deps import get_db
from .routers import (
    activities,
    cached_images,
    categories,
    distance,
    dog_care,
    invites,
    me,
    places,
    plan_links,
    profile,
    stay_compare,
    stays,
    travel,
    trips,
    users,
)

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


def _render(name: str, admin_only: bool = False):
    """One of the app's pages. It is only for people enabled in the app (the page
    itself would just be an empty shell of failing requests otherwise), so the
    rest get a plain explanation instead - with a Log out link, because the
    likeliest cause is being signed in with the wrong address.
    shared_assets_base is baked in server-side (no client-side fetch, no flash
    of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
    before the StaticFiles mount below so these take priority over it."""

    def handler(request: Request, db: Session = Depends(get_db)):
        email = signed_in_email(request)
        user, problem = crud.user_for_request(db, email)
        if user is None:
            message = NO_ACCESS[problem]
            heading = "Your access was removed" if problem == "removed" else "You don't have access yet"
        elif admin_only and not is_admin(user):
            message, heading = "Only the app's administrator can see this page.", "Administrators only"
        else:
            return templates.TemplateResponse(request, name, {"shared_assets_base": SHARED_ASSETS_BASE})
        return templates.TemplateResponse(
            request,
            "no_access.html",
            {"shared_assets_base": SHARED_ASSETS_BASE, "heading": heading, "message": message, "email": email},
            status_code=403,
        )

    return handler


app.get("/", response_class=HTMLResponse)(_render("index.html"))
app.get("/activities.html", response_class=HTMLResponse)(_render("activities.html"))
app.get("/places.html", response_class=HTMLResponse)(_render("places.html"))
app.get("/trip.html", response_class=HTMLResponse)(_render("trip.html"))
app.get("/agenda.html", response_class=HTMLResponse)(_render("agenda.html"))
app.get("/compare.html", response_class=HTMLResponse)(_render("compare.html"))
app.get("/invites.html", response_class=HTMLResponse)(_render("invites.html"))
app.get("/profile.html", response_class=HTMLResponse)(_render("profile.html"))
app.get("/users.html", response_class=HTMLResponse)(_render("users.html", admin_only=True))


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


app.include_router(me.router)
app.include_router(invites.router)
app.include_router(invites.app_router)
app.include_router(profile.router)
app.include_router(trips.router)
app.include_router(activities.router)
app.include_router(places.router)
app.include_router(cached_images.router)
app.include_router(stays.router)
app.include_router(stay_compare.router)
app.include_router(travel.router)
app.include_router(dog_care.router)
app.include_router(categories.router)
app.include_router(plan_links.router)
app.include_router(distance.router)
app.include_router(users.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
