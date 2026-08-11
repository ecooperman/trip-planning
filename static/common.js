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

function formatDateRange(startIso, endIso) {
  const start = formatDateBadge(startIso);
  const end = formatDateBadge(endIso);
  if (start && end) return start === end ? start : `${start} - ${end}`;
  return start || end || null;
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
