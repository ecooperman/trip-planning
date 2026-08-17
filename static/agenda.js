// Trip agenda ("production view"): a day-by-day schedule built from each
// activity's scheduled_start/scheduled_end, plus a sidebar of activities
// with no schedule yet. Dragging an activity onto a gap between two
// scheduled items (or the empty space before the first / after the last /
// across a whole open day) schedules it there if it fits, or shows an
// error if it doesn't - see computePlacement/handleDrop below. This page
// is read-focused; editing name/cost/etc. still happens on trip.html.
//
// Drag-and-drop uses Pointer Events (pointerdown/move/up), not native HTML5
// drag-and-drop - the native API never fires from touch input at all, on
// any layout, so it simply doesn't work on a phone. Pointer Events unify
// mouse/touch/pen behind one code path instead. See makeDraggable below.

const ACTIVITIES_API = `${API_BASE}/activities`;

const params = new URLSearchParams(window.location.search);
const tripId = Number(params.get("id"));

let trip = null;
let activities = [];
let stays = [];

// --- date helpers specific to this page ------------------------------------

function nextDayIso(dayIso) {
  const [y, m, d] = dayIso.split("-").map(Number);
  const next = new Date(y, m - 1, d + 1);
  const pad = (n) => String(n).padStart(2, "0");
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
}

function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function dateRangeDays(startIso, endIso) {
  const days = [];
  let cur = toISODate(startIso);
  const end = toISODate(endIso);
  while (cur <= end && days.length < 366) {
    days.push(cur);
    cur = nextDayIso(cur);
  }
  return days;
}

function findStayForDay(dayIso) {
  return stays.find(
    (s) => s.booked && !s.archived && toISODate(s.start_date) <= dayIso && dayIso <= toISODate(s.end_date)
  );
}

// --- gap computation ---------------------------------------------------------

function buildGapsForDay(dayIso, dayActivities) {
  const dayStart = `${dayIso}T00:00:00`;
  const dayEnd = `${nextDayIso(dayIso)}T00:00:00`;

  if (dayActivities.length === 0) {
    return [{ kind: "empty-day", start: dayStart, end: dayEnd }];
  }

  const gaps = [{ kind: "before-first", start: dayStart, end: dayActivities[0].scheduled_start }];
  for (let i = 0; i < dayActivities.length - 1; i++) {
    gaps.push({ kind: "between", start: dayActivities[i].scheduled_end, end: dayActivities[i + 1].scheduled_start });
  }
  gaps.push({ kind: "after-last", start: dayActivities[dayActivities.length - 1].scheduled_end, end: dayEnd });
  return gaps;
}

// Where in a gap a newly-placed activity should land. "before-first" anchors
// to the END of the gap (finishes right as the next thing starts); "empty-day"
// defaults to 9am if the activity fits after that, else falls back to
// midnight; everything else anchors to the START of the gap (right after
// the preceding activity ends).
function computePlacement(gap, durationMinutes) {
  if (gap.kind === "before-first") {
    const start = addMinutesISO(gap.end, -durationMinutes);
    return { scheduled_start: start, scheduled_end: gap.end };
  }
  if (gap.kind === "empty-day") {
    const defaultStart = `${toISODate(gap.start)}T09:00:00`;
    const start = minutesBetween(defaultStart, gap.end) >= durationMinutes ? defaultStart : gap.start;
    return { scheduled_start: start, scheduled_end: addMinutesISO(start, durationMinutes) };
  }
  return { scheduled_start: gap.start, scheduled_end: addMinutesISO(gap.start, durationMinutes) };
}

function gapLabel(gap, availableMinutes) {
  const freeText = `${formatDuration(availableMinutes)} free`;
  if (gap.kind === "empty-day") return `Nothing scheduled – ${freeText}`;
  if (gap.kind === "before-first") return `Start of day – ${formatTime(gap.end)} (${freeText})`;
  if (gap.kind === "after-last") return `${formatTime(gap.start)} – end of day (${freeText})`;
  return `${formatTime(gap.start)} – ${formatTime(gap.end)} (${freeText})`;
}

// --- drop handling (shared by drag-and-drop and any future non-drag entry
// point) -----------------------------------------------------------------

async function handleDrop(activityId, gap) {
  const activity = activities.find((a) => a.id === activityId);
  if (!activity) return;

  const durationMinutes =
    activity.scheduled_start && activity.scheduled_end
      ? minutesBetween(activity.scheduled_start, activity.scheduled_end)
      : 60;
  const available = minutesBetween(gap.start, gap.end);

  if (durationMinutes > available) {
    Theme.showMessage(
      `"${activity.name}" needs ${formatDuration(durationMinutes)}, but only ${formatDuration(available)} is free there.`,
      "error"
    );
    return;
  }

  const placement = computePlacement(gap, durationMinutes);
  try {
    await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(placement),
    });
    Theme.showMessage(`Scheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    Theme.showMessage(err.message, "error");
  }
}

async function handleUnschedule(activityId) {
  const activity = activities.find((a) => a.id === activityId);
  if (!activity || !activity.scheduled_start) return;
  try {
    await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheduled_start: null, scheduled_end: null }),
    });
    Theme.showMessage(`Unscheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    Theme.showMessage(err.message, "error");
  }
}

// --- drag and drop (Pointer Events) ------------------------------------------

const DRAG_THRESHOLD_PX = 6;

// Wires a single agenda-entry element up as draggable. Gap elements carry
// their `gap` object directly on the DOM node (set in gapElement below) so
// drop targets are found by hit-testing with elementFromPoint during the
// drag, rather than relying on native dragover/drop events that touch
// input never dispatches.
function makeDraggable(entryEl, activity) {
  entryEl.addEventListener("pointerdown", (startEvent) => {
    if (startEvent.button !== undefined && startEvent.button !== 0) return;
    const pointerId = startEvent.pointerId;
    const startX = startEvent.clientX;
    const startY = startEvent.clientY;
    const rect = entryEl.getBoundingClientRect();
    let ghost = null;
    let dragging = false;
    let currentTarget = null;

    function beginDrag() {
      dragging = true;
      entryEl.classList.add("dragging");
      ghost = entryEl.cloneNode(true);
      ghost.classList.add("agenda-drag-ghost");
      ghost.style.width = `${rect.width}px`;
      document.body.appendChild(ghost);
    }

    function moveGhostTo(x, y) {
      ghost.style.left = `${x - rect.width / 2}px`;
      ghost.style.top = `${y - 24}px`;
    }

    function findDropTarget(x, y) {
      ghost.style.display = "none";
      const under = document.elementFromPoint(x, y);
      ghost.style.display = "";
      if (!under) return null;
      const gapEl = under.closest(".agenda-gap:not(.agenda-gap-none)");
      if (gapEl && gapEl._gapData) return { el: gapEl, kind: "gap", gap: gapEl._gapData };
      const unscheduledZone = under.closest("#unscheduled-list");
      if (unscheduledZone) return { el: unscheduledZone, kind: "unscheduled" };
      return null;
    }

    function onMove(e) {
      if (e.pointerId !== pointerId) return;
      if (!dragging) {
        if (Math.abs(e.clientX - startX) < DRAG_THRESHOLD_PX && Math.abs(e.clientY - startY) < DRAG_THRESHOLD_PX) return;
        beginDrag();
      }
      e.preventDefault();
      moveGhostTo(e.clientX, e.clientY);

      const target = findDropTarget(e.clientX, e.clientY);
      if (currentTarget && currentTarget.el !== target?.el) currentTarget.el.classList.remove("drag-over");
      if (target) target.el.classList.add("drag-over");
      currentTarget = target;
    }

    function cleanup() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      if (ghost) ghost.remove();
      entryEl.classList.remove("dragging");
      if (currentTarget) currentTarget.el.classList.remove("drag-over");
    }

    function onUp(e) {
      if (e.pointerId !== pointerId) return;
      const finalTarget = currentTarget;
      cleanup();
      if (dragging && finalTarget) {
        if (finalTarget.kind === "gap") handleDrop(activity.id, finalTarget.gap);
        else handleUnschedule(activity.id);
      }
    }

    function onCancel(e) {
      if (e.pointerId !== pointerId) return;
      cleanup();
    }

    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
  });
}

// --- rendering -----------------------------------------------------------------

function agendaEntryElement(activity) {
  // Reflects (doesn't toggle) done state - marking done happens on the
  // activity's own card on trip.html/activities.html. No checkbox here:
  // the whole entry is a pointerdown-based drag handle (see makeDraggable
  // below), and a nested control would fight that the same way it would
  // fight expand/collapse on the item-card summary.
  const entry = Theme.el("div", { class: "agenda-entry" + (activity.done ? " done" : "") });

  if (activity.scheduled_start) {
    entry.appendChild(
      Theme.el("div", {
        class: "agenda-entry-time",
        text: `${formatTime(activity.scheduled_start)} – ${formatTime(activity.scheduled_end)}`,
      })
    );
  }
  entry.appendChild(Theme.el("div", { class: "agenda-entry-name", text: activity.name }));

  const badges = Theme.el("div", { class: "agenda-entry-badges" });
  const cost = formatCost(activity.cost);
  if (cost) badges.appendChild(Theme.el("span", { class: "item-badge item-badge-cost", text: cost }));
  if (activity.confirmation_number) {
    badges.appendChild(Theme.el("span", { class: "item-badge item-badge-muted", text: `# ${activity.confirmation_number}` }));
  }
  if (badges.children.length) entry.appendChild(badges);

  const links = Theme.el("div", { class: "agenda-entry-links" });
  if (activity.url) links.appendChild(Theme.el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "agenda-entry-link", text: "Open link →" }));
  if (activity.map_link) links.appendChild(Theme.el("a", { href: activity.map_link, target: "_blank", rel: "noopener noreferrer", class: "agenda-entry-link", text: "Map →" }));

  // Directions are always "from wherever you are right now" to this
  // activity's own location - the same link on every entry, scheduled or
  // not, rather than the old "Next"/"Stay" variants (which pointed at the
  // *next* activity or the day's stay - confusing since the label didn't
  // say where "next" actually was). Getting back to the stay now lives
  // solely on the day header / sticky banner link, which also opens
  // directions - no need to duplicate it on every entry too.
  const dest = locationQueryFor(activity);
  links.appendChild(
    Theme.el("a", {
      href: googleMapsDirectionsUrl(dest),
      target: "_blank",
      rel: "noopener noreferrer",
      class: "agenda-entry-link agenda-entry-directions",
      text: "Directions →",
      onclick: (e) => openGoogleMapsPreferringApp(e, "directions", dest),
    })
  );

  if (links.children.length) entry.appendChild(links);

  makeDraggable(entry, activity);
  return entry;
}

function gapElement(gap) {
  const available = minutesBetween(gap.start, gap.end);
  const gapEl = Theme.el("div", { class: "agenda-gap" });

  if (available <= 0) {
    gapEl.classList.add("agenda-gap-none");
    return gapEl;
  }

  gapEl.appendChild(Theme.el("span", { class: "agenda-gap-label", text: gapLabel(gap, available) }));
  gapEl._gapData = gap;
  return gapEl;
}

function renderDayColumn(dayIso) {
  const dayActivities = activities
    .filter((a) => a.scheduled_start && toISODate(a.scheduled_start) === dayIso)
    .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));

  const column = Theme.el("div", { class: "agenda-day", "data-day": dayIso });

  const header = Theme.el("div", { class: "agenda-day-header" });
  header.appendChild(Theme.el("div", { class: "agenda-day-date", text: formatDateBadge(`${dayIso}T00:00:00`) }));
  // Just the name here - the address/directions link lives once in the
  // stay summary above the day columns (see renderStaySummary) rather than
  // being repeated on every day.
  const stay = findStayForDay(dayIso);
  if (stay) header.appendChild(Theme.el("div", { class: "agenda-day-stay", text: `📍 ${stay.name}` }));
  column.appendChild(header);

  const gaps = buildGapsForDay(dayIso, dayActivities);
  column.appendChild(gapElement(gaps[0]));
  dayActivities.forEach((activity, i) => {
    column.appendChild(agendaEntryElement(activity));
    column.appendChild(gapElement(gaps[i + 1]));
  });

  return column;
}

function renderUnscheduledList() {
  const list = document.getElementById("unscheduled-list");
  list.innerHTML = "";
  const unscheduled = activities.filter((a) => !a.scheduled_start);
  document.getElementById("unscheduled-empty").hidden = unscheduled.length !== 0;
  for (const activity of unscheduled) {
    list.appendChild(agendaEntryElement(activity));
  }
}

// --- sticky stay summary --------------------------------------------------
//
// A static list of every booked stay on the trip, each with its own
// directions link and date range - shown once above the day columns rather
// than swapping between them as you scroll (which only ever showed one
// stay at a time and got ambiguous right at the handoff between two
// stays). Each day's own header still names which stay it belongs to (see
// renderDayColumn) - the address/directions link lives here instead of
// being repeated on every single day.

function renderStaySummary() {
  const banner = document.getElementById("stay-banner");
  banner.innerHTML = "";

  const activeStays = stays
    .filter((s) => s.booked && !s.archived)
    .slice()
    .sort((a, b) => a.start_date.localeCompare(b.start_date));

  if (!activeStays.length) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");

  for (const stay of activeStays) {
    const entry = Theme.el("div", { class: "stay-banner-entry" });
    entry.appendChild(Theme.el("span", { class: "stay-banner-pin", "aria-hidden": "true", text: "📍" }));
    entry.appendChild(
      stay.address
        ? Theme.el("a", {
            href: googleMapsDirectionsUrl(stay.address),
            target: "_blank",
            rel: "noopener noreferrer",
            class: "stay-banner-link",
            text: `${stay.name} — ${stay.address}`,
            onclick: (e) => openGoogleMapsPreferringApp(e, "directions", stay.address),
          })
        : Theme.el("span", { class: "stay-banner-link", text: stay.name })
    );
    const dateLabel = formatDateRange(stay.start_date, stay.end_date);
    if (dateLabel) entry.appendChild(Theme.el("span", { class: "stay-banner-dates", text: dateLabel }));
    banner.appendChild(entry);
  }
}

// --- init ---------------------------------------------------------------------

function renderAgenda() {
  const container = document.getElementById("agenda-days");
  container.innerHTML = "";
  renderStaySummary();

  if (!trip.start_date || !trip.end_date) {
    container.appendChild(
      Theme.el("p", { class: "empty-state", text: "Set both a start and end date on this trip (on the trip page) to see the day-by-day agenda." })
    );
  } else {
    const days = dateRangeDays(trip.start_date, trip.end_date);
    for (const dayIso of days) container.appendChild(renderDayColumn(dayIso));

    const today = todayIso();
    const initialDay = today < days[0] ? days[0] : today > days[days.length - 1] ? days[days.length - 1] : today;
    const initialCol = container.querySelector(`[data-day="${initialDay}"]`);
    if (initialCol) container.scrollLeft = initialCol.offsetLeft - container.offsetLeft;
  }

  renderUnscheduledList();
}

async function loadAgenda() {
  [trip, activities, stays] = await Promise.all([
    fetchJSON(`${TRIPS_API}/${tripId}`),
    fetchJSON(`${TRIPS_API}/${tripId}/activities`),
    fetchJSON(`${TRIPS_API}/${tripId}/stays`),
  ]);
  document.getElementById("page-title").textContent = `${trip.location} — Agenda`;
  document.getElementById("back-link").href = `trip.html?id=${tripId}`;
  renderAgenda();
}

async function init() {
  if (!tripId) {
    Theme.showMessage("No trip specified.", "error");
    return;
  }
  try {
    await loadAgenda();
  } catch (err) {
    Theme.showMessage(err.message, "error");
  }
}

init();
