// Shared across every page (index.html, activities.html, trip.html) -
// fetch/DOM helpers and formatting, so page-specific scripts only contain
// what's actually different between them.

const API_BASE = "/api";
const TRIPS_API = `${API_BASE}/trips`;
const CITIES_API = `${API_BASE}/activities/cities`;
const CATEGORIES_API = `${API_BASE}/categories`;

// A user-managed label (name + color) an activity or place can carry zero,
// one, or several of at once (category_ids). Fetched once into module
// state rather than nested on every activity/place from the API - every
// page that needs it (activities.html/trip.html via activity-shared.js,
// agenda.html, places.html) should `await loadCategoriesCache()` before
// building any card/form that reads it. Used to live as a near-identical
// copy in both activity-shared.js and agenda.js (they're never loaded on
// the same page, so it never collided, but it was still the same code
// twice) - places.js needing it too was the actual reason to finally
// share one copy here.
let categories = [];
let categoriesById = {};

async function loadCategoriesCache() {
  categories = await Global.fetchJSON(CATEGORIES_API);
  categoriesById = {};
  for (const category of categories) categoriesById[category.id] = category;
  return categories;
}

// Whether a list of category ids should tint a whole row/card a single
// color (see .item-card.has-category/.agenda-entry.has-category-fill in
// style.css) - only when there's exactly one to tint with. Zero categories
// obviously has nothing to tint with; two or more has no single right
// answer for which color wins, so those both fall back to per-category
// badges instead (see categoryBadgeElements) rather than an arbitrary
// "first one" choice.
function soleCategoryFor(categoryIds) {
  if (!categoryIds || categoryIds.length !== 1) return null;
  return categoriesById[categoryIds[0]] || null;
}

// One small "● Name" badge per assigned category - deliberately quiet
// (a colored dot, not the category's own color as the badge's own fill),
// the same treatment agenda.js originally used for a *scheduled* entry
// (too many differently-colored full-fill rows side by side got noisy) -
// now the general fallback here whenever a row/card doesn't get the
// single-category whole-tint treatment (soleCategoryFor returned null).
function categoryBadgeElements(categoryIds) {
  return (categoryIds || [])
    .map((id) => categoriesById[id])
    .filter(Boolean)
    .map((category) => {
      const badge = Global.el("span", { class: "item-badge category-badge" }, [
        Global.el("span", { class: "category-dot", "aria-hidden": "true" }),
        category.name,
      ]);
      badge.style.setProperty("--cat-color", category.color);
      return badge;
    });
}

// A multiselect of every category (see Global.buildMultiSelect,
// shared-assets) for an activity's/place's own category_ids field -
// returns a {element, getSelectedIds()} wrapper, the same shape
// buildFilterableLocationPicker's pickers already use, rather than a
// plain <select>'s .value (a multiselect has no single "value").
function buildCategoryMultiSelect(selectedIds) {
  let selected = new Set((selectedIds || []).map(String));
  const element = Global.buildMultiSelect({
    options: categories.map((c) => ({ value: c.id, label: c.name, color: c.color })),
    selected: [...selected],
    placeholder: "No categories",
    onChange: (values) => {
      selected = new Set(values);
    },
  });
  return { element, getSelectedIds: () => [...selected].map(Number) };
}

// fetchJSON/el/showMessage/domainFromUrl/toISODate/dateInputToISO/
// formatDateBadge all moved to https://static.evancooperman.com/theme.js
// (window.Global) - shared with every app rather than duplicated here.
// Everything below is trip-planning-specific: time-of-day-aware datetime
// helpers, Google Maps deep-linking, and the view/edit toggle pattern.

// Every distinct city already in use (both trips' and activities' - see
// crud.get_all_cities), fetched once so the city text input on a trip's
// own form (index.html and trip.html) and an activity's form
// (activities.html/trip.html, via activity-shared.js) can all offer the
// same <datalist> suggestions - a plain text field would otherwise let
// "Toronto" get spelled a few different ways and quietly break the city
// filter. Lives here, not activity-shared.js, since index.html (the
// homepage) needs it too and doesn't load that file. One shared
// <datalist> in the page (built by refreshCityDatalist, appended once to
// <body>) rather than a copy per input - a <datalist> id can be
// referenced by any number of inputs via their own list="..." attribute.
const CITY_DATALIST_ID = "city-datalist";
let cities = [];

async function loadCitiesCache() {
  cities = await Global.fetchJSON(CITIES_API);
  refreshCityDatalist();
  return cities;
}

function refreshCityDatalist() {
  let datalist = document.getElementById(CITY_DATALIST_ID);
  if (!datalist) {
    datalist = Global.el("datalist", { id: CITY_DATALIST_ID });
    document.body.appendChild(datalist);
  }
  datalist.innerHTML = "";
  for (const city of cities) datalist.appendChild(Global.el("option", { value: city }));
}

function cityInputElement(value) {
  return Global.el("input", { type: "text", value: value || "", list: CITY_DATALIST_ID, placeholder: "City" });
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

// A 1-5 rating as filled/empty star glyphs, for a read-only badge (Place
// and Activity cards both use this) - null when there's no rating at all,
// same "don't render a placeholder for absent data" convention as
// formatCost.
function starsDisplay(rating) {
  if (!rating) return null;
  return "★".repeat(rating) + "☆".repeat(5 - rating);
}

// A row of 5 clickable stars standing in for a plain <input> - exposes a
// `.value` property (get/set, 1-5 or null) so it drops into the same
// "read/set .value" code every other form field in this app already uses,
// rather than every caller needing its own bespoke get/set logic. Clicking
// the star that's already the current rating clears it (0/null) instead of
// re-setting the same value - the only way to undo a rating without a
// separate "clear" control.
function ratingInputElement(value) {
  const wrap = Global.el("div", { class: "rating-input" });
  let current = value || 0;
  const starEls = [];

  function refresh() {
    starEls.forEach((el, i) => {
      el.textContent = i < current ? "★" : "☆";
      el.classList.toggle("filled", i < current);
    });
  }

  for (let i = 0; i < 5; i++) {
    const star = Global.el("button", {
      type: "button",
      class: "rating-star",
      "aria-label": `${i + 1} star${i === 0 ? "" : "s"}`,
      onclick: () => {
        current = current === i + 1 ? 0 : i + 1;
        refresh();
      },
    });
    starEls.push(star);
    wrap.appendChild(star);
  }
  refresh();

  Object.defineProperty(wrap, "value", {
    get: () => current || null,
    set: (v) => {
      current = v || 0;
      refresh();
    },
  });
  return wrap;
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
// used. An activity with several categories sorts by whichever of them
// comes first in that order (its best/earliest placement, not an average
// or a "primary" pick - there's no such concept, see models.Category).
// Uncategorized activities sort after every real category, keeping their
// own relative order. A plain stable sort (native Array.prototype.sort is
// stable in every engine this app runs in) rather than a bucket/group-by,
// so ties (same category, or both uncategorized) keep whatever order the
// list was already in - "default order" within each group, not re-shuffled.
function sortActivitiesByCategory(activities, categoriesByIdMap) {
  const orderFor = (activity) => {
    const orders = (activity.category_ids || [])
      .map((id) => categoriesByIdMap[id]?.sort_order)
      .filter((order) => order !== undefined);
    return orders.length ? Math.min(...orders) : Infinity;
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
