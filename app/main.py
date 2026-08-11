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

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
