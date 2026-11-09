"""Telling people things - the sending lives in shared_python.notify; this is
where Trip Planning's own wording and links go."""
from typing import Optional

from shared_python import notify as shared
from shared_python.notify import describe_failure, notify, send_email  # noqa: F401 - re-exported

from . import config

APP_NAME = "Trip Planning"


def invite_requested(inviter_email: str, invitee_email: str, role: str) -> None:
    """Tell the administrator a trip's owner asked for someone to be let in."""
    shared.invite_requested("Trips", inviter_email, invitee_email, role, f"{config.PUBLIC_URL}/invites.html")


def tell_given_access(
    to: str, inviter_email: str, trip_name: str, trip_id: Optional[int], role: str, new_person: bool
) -> None:
    """Email someone that they've been given access to a trip."""
    url = f"{config.PUBLIC_URL}/trip.html?id={trip_id}" if trip_id is not None else None
    shared.tell_given_access(to, inviter_email, "trip", trip_name, url, role, new_person, APP_NAME)
