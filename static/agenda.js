// Trip agenda ("production view"): a day-by-day schedule built from each
// activity's scheduled_start/scheduled_end, plus a sidebar of activities
// with no schedule yet. Each free stretch of a day (before the first
// activity, between two, after the last, or the whole day if nothing's
// scheduled yet) is rendered as a run of 30-minute drop slots - dragging an
// activity onto one sets its start to exactly that slot, if its duration
// fits before the next scheduled thing - see buildSlotsForGap/handleDrop
// below. This page is read-focused; editing name/cost/etc. still happens
// on trip.html.
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

// --- lock toggle -----------------------------------------------------------
//
// Locked by default on every page load (not persisted - reloading always
// starts locked again) so that just browsing the agenda on a phone can't
// accidentally reschedule something with a stray touch-drag. The lock
// gates drag-and-drop at the source (see makeDraggable's pointerdown
// handler below) - a body class drives the CSS-only side (dashed slot
// borders, grab cursor) so the calendar visually stops looking
// interactive too, not just stops behaving that way.
let agendaLocked = true;

function updateLockUI() {
  document.body.classList.toggle("agenda-locked", agendaLocked);
  const btn = document.getElementById("lock-toggle");
  btn.classList.toggle("agenda-lock-btn-unlocked", !agendaLocked);
  btn.setAttribute("aria-pressed", String(!agendaLocked));
  btn.innerHTML = "";
  btn.appendChild(Global.el("span", { class: "btn-icon", "data-icon": agendaLocked ? "lock" : "unlock", "aria-hidden": "true" }));
  btn.appendChild(document.createTextNode(agendaLocked ? " Locked" : " Unlocked"));
  applyIcons(btn);
}

function initLockToggle() {
  document.getElementById("lock-toggle").addEventListener("click", () => {
    agendaLocked = !agendaLocked;
    updateLockUI();
  });
  updateLockUI();
}

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
  let cur = Global.toISODate(startIso);
  const end = Global.toISODate(endIso);
  while (cur <= end && days.length < 366) {
    days.push(cur);
    cur = nextDayIso(cur);
  }
  return days;
}

function findStayForDay(dayIso) {
  return stays.find(
    (s) => s.booked && !s.archived && Global.toISODate(s.start_date) <= dayIso && dayIso <= Global.toISODate(s.end_date)
  );
}

// --- gap computation ---------------------------------------------------------

// Slots (and the "before-first"/"empty-day" gaps that generate them) start
// no earlier than this hour - scheduling something at 2am is rare enough
// that showing 8 dead hours of slots before it isn't worth the scrolling.
// An activity already scheduled earlier than this (an early flight, say)
// still displays fine - it just won't get its own drop slots before it.
const DAY_SLOTS_START_HOUR = 8;

function buildGapsForDay(dayIso, dayActivities) {
  const dayStart = `${dayIso}T${String(DAY_SLOTS_START_HOUR).padStart(2, "0")}:00:00`;
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

// --- 30-minute drop slots -----------------------------------------------------
//
// Each free gap is subdivided into 30-minute slots so dropping an activity
// picks its exact start time directly, rather than the old behavior of
// anchoring to a whole gap's edge (start of gap, end of gap, or a 9am
// default) and needing the date/time picker afterward to fine-tune it. A
// slot's own start IS the placement - see handleDrop. The last slot in a
// gap is often shorter than 30 minutes (whatever's left before the gap
// ends) - still a valid drop target for anything short enough to fit.
const SLOT_MINUTES = 30;

function buildSlotsForGap(gap) {
  const slots = [];
  let cursor = gap.start;
  while (minutesBetween(cursor, gap.end) > 0) {
    slots.push({ start: cursor, gapEnd: gap.end });
    cursor = addMinutesISO(cursor, SLOT_MINUTES);
  }
  return slots;
}

// --- drop handling (shared by drag-and-drop and any future non-drag entry
// point) -----------------------------------------------------------------

async function handleDrop(activityId, slot) {
  const activity = activities.find((a) => a.id === activityId);
  if (!activity) return;

  const durationMinutes =
    activity.scheduled_start && activity.scheduled_end
      ? minutesBetween(activity.scheduled_start, activity.scheduled_end)
      : 60;
  const available = minutesBetween(slot.start, slot.gapEnd);

  if (durationMinutes > available) {
    Global.showMessage(
      `"${activity.name}" needs ${formatDuration(durationMinutes)}, but only ${formatDuration(available)} is free there.`,
      "error"
    );
    return;
  }

  const placement = { scheduled_start: slot.start, scheduled_end: addMinutesISO(slot.start, durationMinutes) };
  try {
    await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(placement),
    });
    Global.showMessage(`Scheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

async function handleUnschedule(activityId) {
  const activity = activities.find((a) => a.id === activityId);
  if (!activity || !activity.scheduled_start) return;
  try {
    await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheduled_start: null, scheduled_end: null }),
    });
    Global.showMessage(`Unscheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

// --- drag and drop (Pointer Events) ------------------------------------------

const DRAG_THRESHOLD_PX = 6;
// How close to the top/bottom edge of a day's scrollable slot list (see
// .agenda-day-body) the pointer needs to be to auto-scroll it, and how
// fast - a day can hold 32+ half-hour slots, more than fit in the capped
// height, so without this you'd have to drop partway, then drag again to
// reach further down.
const AUTO_SCROLL_EDGE_PX = 36;
const AUTO_SCROLL_SPEED_PX = 10;

// Wires a single agenda-entry element up as draggable. Slot elements carry
// their `slot` object directly on the DOM node (set in slotElement below) so
// drop targets are found by hit-testing with elementFromPoint during the
// drag, rather than relying on native dragover/drop events that touch
// input never dispatches.
function makeDraggable(entryEl, activity) {
  entryEl.addEventListener("pointerdown", (startEvent) => {
    if (agendaLocked) return;
    if (startEvent.button !== undefined && startEvent.button !== 0) return;
    const pointerId = startEvent.pointerId;
    const startX = startEvent.clientX;
    const startY = startEvent.clientY;
    const rect = entryEl.getBoundingClientRect();
    let ghost = null;
    let dragging = false;
    let currentTarget = null;
    let originDayIso = null;
    let lastX = startX;
    let lastY = startY;
    let rafId = null;

    function beginDrag() {
      dragging = true;
      entryEl.classList.add("dragging");
      ghost = entryEl.cloneNode(true);
      ghost.classList.add("agenda-drag-ghost");
      ghost.style.width = `${rect.width}px`;
      document.body.appendChild(ghost);

      // If this activity is already scheduled, re-render its own day with
      // it excluded (see renderDayColumn) so slots open up in its current
      // span too - otherwise a same-day nudge always collides with itself.
      // cleanup() reverts this once the drag ends, whether it succeeds,
      // fails validation, or is cancelled.
      if (activity.scheduled_start) {
        originDayIso = Global.toISODate(activity.scheduled_start);
        const oldCol = document.querySelector(`.agenda-day[data-day="${originDayIso}"]`);
        if (oldCol) oldCol.replaceWith(renderDayColumn(originDayIso, { excludeActivityId: activity.id }));
      }

      rafId = requestAnimationFrame(tick);
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
      const slotEl = under.closest(".agenda-slot");
      if (slotEl && slotEl._slotData) return { el: slotEl, kind: "slot", slot: slotEl._slotData };
      const unscheduledZone = under.closest("#unscheduled-list");
      if (unscheduledZone) return { el: unscheduledZone, kind: "unscheduled" };
      return null;
    }

    // Scrolls whichever day's slot list the pointer is currently over, if
    // it's near that list's top/bottom edge. A day can hold more slots
    // than fit in its capped height (see .agenda-day-body), so this is
    // what lets you reach a slot further down without dropping partway,
    // then dragging a second time to cover the rest.
    function autoScrollNear(x, y) {
      for (const body of document.querySelectorAll(".agenda-day-body")) {
        const r = body.getBoundingClientRect();
        if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
        if (y - r.top < AUTO_SCROLL_EDGE_PX) body.scrollTop -= AUTO_SCROLL_SPEED_PX;
        else if (r.bottom - y < AUTO_SCROLL_EDGE_PX) body.scrollTop += AUTO_SCROLL_SPEED_PX;
        return;
      }
    }

    // Auto-scrolls and re-highlights the drop target for the pointer's
    // current position. Called both directly on every real pointermove
    // (so motion feels immediate) and every animation frame for the life
    // of the drag (so it keeps going, and the highlight keeps updating,
    // even while the pointer holds still near an edge - content is moving
    // under it even though the pointer itself isn't).
    function updateDragState() {
      autoScrollNear(lastX, lastY);

      const target = findDropTarget(lastX, lastY);
      if (currentTarget && currentTarget.el !== target?.el) currentTarget.el.classList.remove("drag-over");
      if (target) target.el.classList.add("drag-over");
      currentTarget = target;
    }

    function tick() {
      if (!dragging) return;
      updateDragState();
      rafId = requestAnimationFrame(tick);
    }

    function onMove(e) {
      if (e.pointerId !== pointerId) return;
      lastX = e.clientX;
      lastY = e.clientY;
      if (!dragging) {
        if (Math.abs(e.clientX - startX) < DRAG_THRESHOLD_PX && Math.abs(e.clientY - startY) < DRAG_THRESHOLD_PX) return;
        beginDrag();
      }
      e.preventDefault();
      moveGhostTo(lastX, lastY);
      updateDragState();
    }

    function cleanup() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      if (rafId) cancelAnimationFrame(rafId);
      if (ghost) ghost.remove();
      entryEl.classList.remove("dragging");
      if (currentTarget) currentTarget.el.classList.remove("drag-over");

      // Undo the origin-day swap from beginDrag - if the drop below
      // succeeds, loadAgenda() re-renders everything moments later anyway;
      // if it fails validation or the drag was cancelled, this puts the
      // activity's own entry/slots straight back rather than leaving it
      // looking like it vanished from its day.
      if (originDayIso) {
        const col = document.querySelector(`.agenda-day[data-day="${originDayIso}"]`);
        if (col) col.replaceWith(renderDayColumn(originDayIso));
      }
    }

    function onUp(e) {
      if (e.pointerId !== pointerId) return;
      const finalTarget = currentTarget;
      cleanup();
      if (dragging && finalTarget) {
        if (finalTarget.kind === "slot") handleDrop(activity.id, finalTarget.slot);
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
  const entry = Global.el("div", { class: "agenda-entry" + (activity.done ? " done" : "") });

  if (activity.scheduled_start) {
    entry.appendChild(
      Global.el("div", {
        class: "agenda-entry-time",
        text: `${formatTime(activity.scheduled_start)} – ${formatTime(activity.scheduled_end)}`,
      })
    );
  }
  entry.appendChild(Global.el("div", { class: "agenda-entry-name", text: activity.name }));

  const badges = Global.el("div", { class: "agenda-entry-badges" });
  const cost = formatCost(activity.cost);
  if (cost) badges.appendChild(Global.el("span", { class: "item-badge item-badge-cost", text: cost }));
  if (activity.confirmation_number) {
    badges.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: `# ${activity.confirmation_number}` }));
  }
  if (badges.children.length) entry.appendChild(badges);

  const links = Global.el("div", { class: "agenda-entry-links" });
  if (activity.url) links.appendChild(Global.el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "agenda-entry-link", text: "Open link →" }));
  if (activity.map_link) links.appendChild(Global.el("a", { href: activity.map_link, target: "_blank", rel: "noopener noreferrer", class: "agenda-entry-link", text: "Map →" }));

  // Directions are always "from wherever you are right now" to this
  // activity's own location - the same link on every entry, scheduled or
  // not, rather than the old "Next"/"Stay" variants (which pointed at the
  // *next* activity or the day's stay - confusing since the label didn't
  // say where "next" actually was). Getting back to the stay now lives
  // solely on the day header / sticky banner link, which also opens
  // directions - no need to duplicate it on every entry too.
  const dest = locationQueryFor(activity);
  links.appendChild(
    Global.el("a", {
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

function slotElement(slot) {
  const slotEl = Global.el("div", { class: "agenda-slot" });
  slotEl.appendChild(Global.el("span", { class: "agenda-slot-time", text: formatTime(slot.start) }));
  slotEl._slotData = slot;
  return slotEl;
}

// excludeActivityId lets a same-day drag treat the activity being moved as
// if it were still unscheduled while computing gaps/slots - otherwise its
// own current time span counts as an obstacle against itself, so nudging
// it by less than its own duration always looks like a collision (the gap
// on either side stops right at its own old start/end, not at whatever
// genuinely comes next). See makeDraggable, which re-renders the origin
// day with this set for the duration of the drag, then reverts it.
function renderDayColumn(dayIso, { excludeActivityId = null } = {}) {
  const dayActivities = activities
    .filter((a) => a.scheduled_start && Global.toISODate(a.scheduled_start) === dayIso && a.id !== excludeActivityId)
    .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));

  const column = Global.el("div", { class: "agenda-day", "data-day": dayIso });

  const header = Global.el("div", { class: "agenda-day-header" });
  header.appendChild(Global.el("div", { class: "agenda-day-date", text: Global.formatDateBadge(`${dayIso}T00:00:00`) }));
  // Just the name here - the address/directions link lives once in the
  // stay summary above the day columns (see renderStaySummary) rather than
  // being repeated on every day.
  const stay = findStayForDay(dayIso);
  if (stay) header.appendChild(Global.el("div", { class: "agenda-day-stay", text: `📍 ${stay.name}` }));
  column.appendChild(header);

  // Everything below the header scrolls independently (see
  // .agenda-day-body in style.css) - an all-day-free column renders 48
  // half-hour slots, and without its own scroll container that one column
  // would force every other day in the row to stretch to match it.
  const body = Global.el("div", { class: "agenda-day-body" });

  // Every gap (before the first activity, between two, after the last, or
  // the whole day if nothing's scheduled) renders as a run of 30-min slots
  // rather than one big drop target - see buildSlotsForGap.
  const gaps = buildGapsForDay(dayIso, dayActivities);
  gaps.forEach((gap, i) => {
    for (const slot of buildSlotsForGap(gap)) body.appendChild(slotElement(slot));
    const activity = dayActivities[i];
    if (activity) body.appendChild(agendaEntryElement(activity));
  });
  column.appendChild(body);

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
    const entry = Global.el("div", { class: "stay-banner-entry" });
    entry.appendChild(Global.el("span", { class: "stay-banner-pin", "aria-hidden": "true", text: "📍" }));
    entry.appendChild(
      stay.address
        ? Global.el("a", {
            href: googleMapsDirectionsUrl(stay.address),
            target: "_blank",
            rel: "noopener noreferrer",
            class: "stay-banner-link",
            text: `${stay.name} — ${stay.address}`,
            onclick: (e) => openGoogleMapsPreferringApp(e, "directions", stay.address),
          })
        : Global.el("span", { class: "stay-banner-link", text: stay.name })
    );
    const dateLabel = formatDateRange(stay.start_date, stay.end_date);
    if (dateLabel) entry.appendChild(Global.el("span", { class: "stay-banner-dates", text: dateLabel }));
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
      Global.el("p", { class: "empty-state", text: "Set both a start and end date on this trip (on the trip page) to see the day-by-day agenda." })
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
    Global.fetchJSON(`${TRIPS_API}/${tripId}`),
    Global.fetchJSON(`${TRIPS_API}/${tripId}/activities`),
    Global.fetchJSON(`${TRIPS_API}/${tripId}/stays`),
  ]);
  document.getElementById("page-title").textContent = `${trip.location} — Agenda`;
  document.getElementById("back-link").href = `trip.html?id=${tripId}`;
  document.getElementById("export-link").href = `${TRIPS_API}/${tripId}/export.xlsx`;
  renderAgenda();
}

async function init() {
  initLockToggle();
  if (!tripId) {
    Global.showMessage("No trip specified.", "error");
    return;
  }
  try {
    await loadAgenda();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

init();
