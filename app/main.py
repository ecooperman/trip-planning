from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import activities, stays, trips

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

app = FastAPI(title="Trip Planning")

app.include_router(trips.router)
app.include_router(activities.router)
app.include_router(stays.router)


class NoCacheStaticFiles(StaticFiles):
    """Plain StaticFiles sends no Cache-Control header at all, which makes
    browsers apply their own heuristic caching (roughly 10% of the file's
    age since Last-Modified) - in practice that means a deployed JS/CSS
    change can silently not show up for a user with the old version
    already cached, with no way to tell short of a hard refresh. `no-cache`
    (not `no-store`) still lets the browser use its cached copy, but only
    after revalidating with the server via the ETag/Last-Modified headers
    StaticFiles already sends - a cheap 304 when nothing changed, the real
    file when something did.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", NoCacheStaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
