// Shared across every page (index.html, activities.html, trip.html) -
// fetch/DOM helpers and formatting, so page-specific scripts only contain
// what's actually different between them.

const API_BASE = "/api";
const TRIPS_API = `${API_BASE}/trips`;

// fetchJSON/el/showMessage/domainFromUrl/toISODate/dateInputToISO/
// formatDateBadge all moved to https://static.evancooperman.com/theme.js
// (window.Global) - shared with every app rather than duplicated here.
// Everything below is trip-planning-specific: time-of-day-aware datetime
// helpers, Google Maps deep-linking, and the view/edit toggle pattern.

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
  const dateLabel = Global.formatDateBadge(startIso);
  const startTime = formatTime(startIso);
  if (!endIso) return `${dateLabel}, ${startTime}`;
  const sameDay = Global.toISODate(startIso) === Global.toISODate(endIso);
  const endTime = formatTime(endIso);
  return sameDay ? `${dateLabel}, ${startTime}–${endTime}` : `${dateLabel} ${startTime} – ${Global.formatDateBadge(endIso)} ${endTime}`;
}

function formatDateRange(startIso, endIso) {
  const start = Global.formatDateBadge(startIso);
  const end = Global.formatDateBadge(endIso);
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

function isYelpUrl(url) {
  const domain = Global.domainFromUrl(url);
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

function isIOSDevice() {
  if (/iPad|iPhone|iPod/.test(navigator.userAgent)) return true;
  // iPadOS 13+ can report as "MacIntel" (a desktop Safari UA) unless
  // "Request Desktop Website" is off - multi-touch is the giveaway a real
  // Mac doesn't have.
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

function isAndroidDevice() {
  return /Android/.test(navigator.userAgent);
}

// Wire this as an onclick alongside an href of the plain googleMapsSearchUrl/
// googleMapsDirectionsUrl web URL (so the link still works if this can't
// run) on any link built from those two functions. On desktop it's a no-op
// - the plain href already does the right thing.
//
// On phones, it prefers the installed Google Maps app over the mobile web
// view via Google's own app-specific URL schemes - this matters a lot from
// a home-screen PWA, where Universal/App Links (which normally hand a
// plain https://maps.google.com/... link off to the app in a regular
// browser tab) frequently don't fire the same way, leaving you stuck in
// the cramped web view instead of the real app.
//
// `kind` is "search" (just show a place) or "directions" (route to it,
// origin omitted so it defaults to current location); `query` is an
// address or place name - the same input already passed to
// googleMapsSearchUrl/googleMapsDirectionsUrl for the href.
function openGoogleMapsPreferringApp(e, kind, query) {
  if (!isIOSDevice() && !isAndroidDevice()) return; // let the plain <a href> handle desktop

  e.preventDefault();
  const encoded = encodeURIComponent(query);
  const webUrl = kind === "directions" ? googleMapsDirectionsUrl(query) : googleMapsSearchUrl(query);

  if (isAndroidDevice()) {
    // The intent:// scheme has a built-in fallback (S.browser_fallback_url)
    // for "app not installed" - no timing hack needed, unlike iOS below.
    const params = kind === "directions" ? `daddr=${encoded}&directionsmode=driving` : `q=${encoded}`;
    window.location.href =
      `intent://maps.google.com/maps?${params}#Intent;scheme=https;` +
      `package=com.google.android.apps.maps;S.browser_fallback_url=${encodeURIComponent(webUrl)};end`;
    return;
  }

  // iOS custom schemes have no built-in fallback, so do it ourselves: try
  // the app, and if we're still here (foregrounded) shortly after, nothing
  // intercepted it - open the web version instead.
  const appUrl = kind === "directions" ? `comgooglemaps://?daddr=${encoded}&directionsmode=driving` : `comgooglemaps://?q=${encoded}`;
  const start = Date.now();
  window.location.href = appUrl;
  setTimeout(() => {
    if (!document.hidden && Date.now() - start < 2000) {
      window.open(webUrl, "_blank", "noopener,noreferrer");
    }
  }, 1500);
}

// Best-effort text to route to for something that might not have a real
// address on file yet - falls back to its name, which Maps can usually
// still resolve to a real place via search.
function locationQueryFor(record) {
  return record.address || record.name;
}

// --- sort-by-category, shared by activities.js and agenda.js -------------
//
// Groups activities by category, in the same order Manage Categories shows
// them in (category.sort_order - see activities.js's reorderCategory) -
// reordering categories there changes this order too, everywhere it's
// used. Uncategorized activities sort after every real category, keeping
// their own relative order. A plain stable sort (native Array.prototype.sort
// is stable in every engine this app runs in) rather than a bucket/group-by,
// so ties (same category, or both uncategorized) keep whatever order the
// list was already in - "default order" within each group, not re-shuffled.
function sortActivitiesByCategory(activities, categoriesById) {
  const orderFor = (activity) => {
    const category = activity.category_id ? categoriesById[activity.category_id] : null;
    return category ? category.sort_order : Infinity;
  };
  return activities.slice().sort((a, b) => orderFor(a) - orderFor(b));
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
  return Global.el("div", { class: "view-field" }, [
    Global.el("div", { class: "view-field-label", text: label }),
    Global.el("div", { class: "view-field-value", text: value }),
  ]);
}

// Shared trip-deletion flow (used by both index.js and trip.js): asks
// whether to also permanently delete the trip's activities, since keeping
// them around unassociated is the safer default but not always what's
// wanted (e.g. a trip created by mistake, where the "activities" are junk
// too).
async function confirmAndDeleteTrip(trip) {
  const activities = await Global.fetchJSON(`${API_BASE}/trips/${trip.id}/activities`);
  if (!confirm(`Delete trip "${trip.location}"? This cannot be undone.`)) return false;

  let deleteActivities = false;
  if (activities.length > 0) {
    deleteActivities = confirm(
      `This trip has ${activities.length} activit${activities.length === 1 ? "y" : "ies"}. ` +
      `Delete ${activities.length === 1 ? "it" : "them"} too?\n\n` +
      `OK = delete permanently.\nCancel = keep ${activities.length === 1 ? "it" : "them"}, unlinked from any trip.`
    );
  }

  await Global.fetchJSON(`${API_BASE}/trips/${trip.id}?delete_activities=${deleteActivities}`, { method: "DELETE" });
  return true;
}
