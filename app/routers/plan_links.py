"""The trips side of the social-planning <-> trip-planning link.

Plans are the long-lived wishlist (plans.evancooperman.com); a plan turns
into an activity here, never the other way round. Both directions of
"turn a plan into an activity" land on POST /import below - trip.html's
"Import from plans" picker calls it directly, and the plans app's "Send to
trips" button calls it server-to-server - so there's exactly one place
that decides what gets copied and what counts as a duplicate.

The link itself lives only here (Activity.plan_id), never mirrored into
the plans database; the plans app reads it back via GET "" below.

The plans live in the administrator's own social-planning app, so everything
that reads from or writes plans is for the administrator only: signed in as
one, or the plans app itself with the service token (see auth.admin_or_service).
"""
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..access import check_role
from ..auth import admin_or_service, user_or_service
from ..config import PLANS_API_BASE, PLANS_PUBLIC_URL
from ..deps import get_db

router = APIRouter(prefix="/api/plan-links", tags=["plan-links"])


def _plans_get(path: str, params: Optional[dict] = None):
    try:
        resp = requests.get(f"{PLANS_API_BASE}{path}", params=params, timeout=5)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach the plans app: {exc}")
    if resp.status_code == 404:
        return None
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Plans app returned {resp.status_code}")
    return resp.json()


@router.get("", response_model=List[schemas.PlanLink])
def list_plan_links(
    plan_id: Optional[int] = None, user: models.User = Depends(user_or_service), db: Session = Depends(get_db)
):
    links = []
    for activity in crud.get_plan_linked_activities(db, user.id, plan_id):
        trip = activity.trips[0] if activity.trips else None
        links.append(
            schemas.PlanLink(
                plan_id=activity.plan_id,
                activity_id=activity.id,
                activity_name=activity.name,
                done=activity.done,
                archived=activity.archived,
                trip_id=trip.id if trip else None,
                trip_location=trip.location if trip else None,
            )
        )
    return links


@router.get("/locations")
def list_plan_locations(user: models.User = Depends(admin_or_service)):
    return _plans_get("/api/locations")


@router.get("/plans")
def list_plans(
    location_id: Optional[int] = None,
    trip_id: Optional[int] = None,
    user: models.User = Depends(admin_or_service),
    db: Session = Depends(get_db),
):
    """Plans (optionally in one location), each annotated with whether it's
    already an activity on `trip_id` - so the picker can grey those out."""
    params = {"location_id": location_id} if location_id is not None else None
    plans = _plans_get("/api/plans", params) or []
    already = set()
    if trip_id is not None:
        already = {
            a.plan_id
            for a in crud.get_plan_linked_activities(db, user.id)
            if trip_id in [t.id for t in a.trips]
        }
    for plan in plans:
        plan["in_trip"] = plan["id"] in already
        plan["plans_url"] = PLANS_PUBLIC_URL
    return plans


@router.post("/import", response_model=schemas.PlanImportResult)
def import_plans(
    request: schemas.PlanImportRequest, user: models.User = Depends(admin_or_service), db: Session = Depends(get_db)
):
    # Content added to a trip belongs to the trip's owner, even if the
    # administrator is only an editor on it.
    owner_id = user.id
    if request.trip_id is not None:
        member = crud.get_membership(db, user.id, request.trip_id)
        if member is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        check_role(member.role, models.ROLE_EDIT)
        owner_id = member.trip.owner_id

    created, skipped = [], 0
    for plan_id in request.plan_ids:
        if crud.find_plan_activity(db, owner_id, plan_id, request.trip_id) is not None:
            skipped += 1
            continue
        plan = _plans_get(f"/api/plans/{plan_id}")
        if plan is None:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found in the plans app")
        created.append(crud.create_activity_from_plan(db, owner_id, plan, request.trip_id))

    return schemas.PlanImportResult(created=len(created), skipped=skipped, activities=created)
