// Shared across every page (index.html, activities.html, trip.html) -
// fetch/DOM helpers and formatting, so page-specific scripts only contain
// what's actually different between them.

const API_BASE = "/api";
const TRIPS_API = `${API_BASE}/trips`;

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (Array.isArray(body.detail)) {
        // FastAPI/Pydantic 422 validation errors: detail is a list of
        // {loc, msg, ...} objects, not a string - join their messages so
        // the user sees the actual validation complaint instead of
        // "[object Object]".
        detail = body.detail.map((e) => e.msg || JSON.stringify(e)).join("; ");
      } else if (body.detail) {
        detail = body.detail;
      }
    } catch (e) {
      // ignore, use default detail
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function showMessage(text, kind) {
  const el = document.getElementById("page-message");
  if (!el) return;
  el.textContent = text;
  el.className = "page-message " + kind;
  clearTimeout(showMessage._t);
  showMessage._t = setTimeout(() => el.classList.add("hidden"), 4000);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function toISODate(isoDateTime) {
  if (!isoDateTime) return "";
  return isoDateTime.slice(0, 10);
}

function dateInputToISO(value) {
  return value ? `${value}T00:00:00` : null;
}

function formatDateBadge(isoDateTime) {
  if (!isoDateTime) return null;
  const [y, m, d] = isoDateTime.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// --- datetime (date + time-of-day) helpers, for Activity.scheduled_start/
// scheduled_end. Our stored datetimes are naive (no timezone) - they mean
// "this wall-clock time at the destination" - so every helper below parses
// the y/m/d/hh/mm components directly and builds a local Date from them,
// the same way formatDateBadge avoids Date's ISO-string-parsing pitfalls,
// rather than ever doing `new Date(isoString)` on a timezone-less string.

function parseDateTimeParts(isoDateTime) {
  const [datePart, timePart = "00:00:00"] = isoDateTime.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mm] = timePart.split(":").map(Number);
  return { y, m, d, hh, mm };
}

function partsToDate(parts) {
  return new Date(parts.y, parts.m - 1, parts.d, parts.hh, parts.mm);
}

function dateToISODateTime(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}

function minutesBetween(startIso, endIso) {
  return (partsToDate(parseDateTimeParts(endIso)) - partsToDate(parseDateTimeParts(startIso))) / 60000;
}

function addMinutesISO(isoDateTime, minutes) {
  const date = partsToDate(parseDateTimeParts(isoDateTime));
  date.setMinutes(date.getMinutes() + minutes);
  return dateToISODateTime(date);
}

function toDatetimeLocal(isoDateTime) {
  if (!isoDateTime) return "";
  return isoDateTime.slice(0, 16);
}

function datetimeLocalToISO(value) {
  return value ? `${value}:00` : null;
}

function formatTime(isoDateTime) {
  if (!isoDateTime) return null;
  return partsToDate(parseDateTimeParts(isoDateTime)).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatScheduleBadge(startIso, endIso) {
  if (!startIso) return null;
  const dateLabel = formatDateBadge(startIso);
  const startTime = formatTime(startIso);
  if (!endIso) return `${dateLabel}, ${startTime}`;
  const sameDay = toISODate(startIso) === toISODate(endIso);
  const endTime = formatTime(endIso);
  return sameDay ? `${dateLabel}, ${startTime}–${endTime}` : `${dateLabel} ${startTime} – ${formatDateBadge(endIso)} ${endTime}`;
}

function formatDateRange(startIso, endIso) {
  const start = formatDateBadge(startIso);
  const end = formatDateBadge(endIso);
  if (start && end) return start === end ? start : `${start} - ${end}`;
  return start || end || null;
}

function formatDuration(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function formatCost(cost) {
  if (cost === null || cost === undefined) return null;
  return `$${cost.toLocaleString()}`;
}

function domainFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (e) {
    return null;
  }
}

function isYelpUrl(url) {
  const domain = domainFromUrl(url);
  return domain === "yelp.com" || (domain !== null && domain.endsWith(".yelp.com"));
}

// Google's documented cross-platform maps URL - both iOS Safari and
// Android Chrome hand a real tap on this off to the Google Maps app via
// Universal/App Links if it's installed, falling back to the website
// otherwise. Only used for an address we don't already have a map_link
// for (e.g. a Stay's address, or an Activity with no scraped map_link).
function googleMapsSearchUrl(address) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}

// Directions to a destination, deliberately with no `origin` param - Google
// Maps treats an origin-less directions link as "from my current location,"
// which is what you actually want when tapping this while out on the trip
// (a stale address for wherever you started from is less useful and often
// unavailable anyway). Used on the agenda page for "next activity" / "back
// to the stay" links - see agenda.js.
function googleMapsDirectionsUrl(destination) {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}&travelmode=driving`;
}

// Best-effort text to route to for something that might not have a real
// address on file yet - falls back to its name, which Maps can usually
// still resolve to a real place via search.
function locationQueryFor(record) {
  return record.address || record.name;
}

// --- view/edit toggle, used identically by trip/stay/activity cards -----
//
// Convention: each card's details area holds two sibling panes built by
// the caller - a read-only "view pane" (with a button carrying the
// "edit-toggle-btn" class) and a form "edit pane" (with a button carrying
// "cancel-edit-btn"). This just wires the show/hide between them - a plain
// front-end swap of hidden elements, no re-fetch. Cancel is expected to be
// wired by the caller to a full re-render instead of a hide/show (so
// unsaved typing is discarded cleanly rather than lingering hidden in the
// DOM) - see the per-entity buildXEditPane functions.
function wireViewEditToggle(viewPane, editPane) {
  editPane.classList.add("hidden");
  const editBtn = viewPane.querySelector(".edit-toggle-btn");
  if (editBtn) {
    editBtn.addEventListener("click", () => {
      viewPane.classList.add("hidden");
      editPane.classList.remove("hidden");
    });
  }
}

// A single read-only label/value row for a view pane. Returns null (append
// with a guard, or use viewFieldOrNull) when value is empty, so callers can
// write `[viewField(...), viewField(...)].filter(Boolean)` for optional
// fields without a wall of individual `if` statements.
function viewField(label, value) {
  if (!value) return null;
  return el("div", { class: "view-field" }, [
    el("div", { class: "view-field-label", text: label }),
    el("div", { class: "view-field-value", text: value }),
  ]);
}

// Shared trip-deletion flow (used by both index.js and trip.js): asks
// whether to also permanently delete the trip's activities, since keeping
// them around unassociated is the safer default but not always what's
// wanted (e.g. a trip created by mistake, where the "activities" are junk
// too).
async function confirmAndDeleteTrip(trip) {
  const activities = await fetchJSON(`${API_BASE}/trips/${trip.id}/activities`);
  if (!confirm(`Delete trip "${trip.location}"? This cannot be undone.`)) return false;

  let deleteActivities = false;
  if (activities.length > 0) {
    deleteActivities = confirm(
      `This trip has ${activities.length} activit${activities.length === 1 ? "y" : "ies"}. ` +
      `Delete ${activities.length === 1 ? "it" : "them"} too?\n\n` +
      `OK = delete permanently.\nCancel = keep ${activities.length === 1 ? "it" : "them"}, unlinked from any trip.`
    );
  }

  await fetchJSON(`${API_BASE}/trips/${trip.id}?delete_activities=${deleteActivities}`, { method: "DELETE" });
  return true;
}
