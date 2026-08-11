// Trip agenda ("production view"): a day-by-day schedule built from each
// activity's scheduled_start/scheduled_end, plus a sidebar of activities
// with no schedule yet. Dragging an activity onto a gap between two
// scheduled items (or the empty space before the first / after the last /
// across a whole open day) schedules it there if it fits, or shows an
// error if it doesn't - see computePlacement/handleDrop below. This page
// is read-focused; editing name/cost/etc. still happens on trip.html.

const ACTIVITIES_API = `${API_BASE}/activities`;

const params = new URLSearchParams(window.location.search);
const tripId = Number(params.get("id"));

let trip = null;
let activities = [];
let stays = [];
let draggedActivityId = null;

// --- date helpers specific to this page ------------------------------------

function nextDayIso(dayIso) {
  const [y, m, d] = dayIso.split("-").map(Number);
  const next = new Date(y, m - 1, d + 1);
  const pad = (n) => String(n).padStart(2, "0");
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
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

// --- drag and drop -----------------------------------------------------------

async function handleDrop(activityId, gap) {
  const activity = activities.find((a) => a.id === activityId);
  if (!activity) return;

  const durationMinutes =
    activity.scheduled_start && activity.scheduled_end
      ? minutesBetween(activity.scheduled_start, activity.scheduled_end)
      : 60;
  const available = minutesBetween(gap.start, gap.end);

  if (durationMinutes > available) {
    showMessage(
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
    showMessage(`Scheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    showMessage(err.message, "error");
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
    showMessage(`Unscheduled "${activity.name}".`, "success");
    await loadAgenda();
  } catch (err) {
    showMessage(err.message, "error");
  }
}

// --- rendering -----------------------------------------------------------------

function agendaEntryElement(activity) {
  const entry = el("div", { class: "agenda-entry", draggable: "true" });
  entry.addEventListener("dragstart", (e) => {
    draggedActivityId = activity.id;
    e.dataTransfer.effectAllowed = "move";
  });

  if (activity.scheduled_start) {
    entry.appendChild(
      el("div", {
        class: "agenda-entry-time",
        text: `${formatTime(activity.scheduled_start)} – ${formatTime(activity.scheduled_end)}`,
      })
    );
  }
  entry.appendChild(el("div", { class: "agenda-entry-name", text: activity.name }));

  const badges = el("div", { class: "agenda-entry-badges" });
  const cost = formatCost(activity.cost);
  if (cost) badges.appendChild(el("span", { class: "item-badge item-badge-cost", text: cost }));
  if (activity.confirmation_number) {
    badges.appendChild(el("span", { class: "item-badge item-badge-muted", text: `# ${activity.confirmation_number}` }));
  }
  if (badges.children.length) entry.appendChild(badges);

  if (activity.url) {
    entry.appendChild(
      el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "agenda-entry-link", text: "Open link →" })
    );
  }

  return entry;
}

function gapElement(gap) {
  const available = minutesBetween(gap.start, gap.end);
  const gapEl = el("div", { class: "agenda-gap" });

  if (available <= 0) {
    gapEl.classList.add("agenda-gap-none");
    return gapEl;
  }

  gapEl.appendChild(el("span", { class: "agenda-gap-label", text: gapLabel(gap, available) }));
  gapEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    gapEl.classList.add("drag-over");
  });
  gapEl.addEventListener("dragleave", () => gapEl.classList.remove("drag-over"));
  gapEl.addEventListener("drop", (e) => {
    e.preventDefault();
    gapEl.classList.remove("drag-over");
    if (draggedActivityId == null) return;
    const id = draggedActivityId;
    draggedActivityId = null;
    handleDrop(id, gap);
  });

  return gapEl;
}

function renderDayColumn(dayIso) {
  const dayActivities = activities
    .filter((a) => a.scheduled_start && toISODate(a.scheduled_start) === dayIso)
    .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));

  const column = el("div", { class: "agenda-day" });

  const header = el("div", { class: "agenda-day-header" });
  header.appendChild(el("div", { class: "agenda-day-date", text: formatDateBadge(`${dayIso}T00:00:00`) }));
  const stay = findStayForDay(dayIso);
  if (stay) header.appendChild(el("div", { class: "agenda-day-stay", text: `📍 ${stay.name}` }));
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

function renderAgenda() {
  const container = document.getElementById("agenda-days");
  container.innerHTML = "";

  if (!trip.start_date || !trip.end_date) {
    container.appendChild(
      el("p", { class: "empty-state", text: "Set both a start and end date on this trip (on the trip page) to see the day-by-day agenda." })
    );
  } else {
    for (const dayIso of dateRangeDays(trip.start_date, trip.end_date)) {
      container.appendChild(renderDayColumn(dayIso));
    }
  }

  renderUnscheduledList();
}

function initUnscheduledDropZone() {
  const list = document.getElementById("unscheduled-list");
  list.addEventListener("dragover", (e) => {
    e.preventDefault();
    list.classList.add("drag-over");
  });
  list.addEventListener("dragleave", () => list.classList.remove("drag-over"));
  list.addEventListener("drop", (e) => {
    e.preventDefault();
    list.classList.remove("drag-over");
    if (draggedActivityId == null) return;
    const id = draggedActivityId;
    draggedActivityId = null;
    handleUnschedule(id);
  });
}

// --- init -------------------------------------------------------------------

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
    showMessage("No trip specified.", "error");
    return;
  }
  initUnscheduledDropZone();
  try {
    await loadAgenda();
  } catch (err) {
    showMessage(err.message, "error");
  }
}

init();
