// Trip detail page: trip header, stay-coverage banner, stays (inline -
// there's no standalone stays page since a stay always belongs to a trip),
// and activities (via activity-shared.js, the same code as activities.html).
//
// Trip header and stay cards both follow the same view/edit pattern as
// activities: a read-only view with an Edit button, which swaps to the
// form (edit pane) - see wireViewEditToggle in common.js.

const STAYS_API = `${API_BASE}/stays`;

const params = new URLSearchParams(window.location.search);
const tripId = Number(params.get("id"));

let currentTrip = null;
let unassociatedSelect = null;

// --- trip header -----------------------------------------------------------

function renderTripHeader() {
  document.getElementById("page-title").textContent = currentTrip.location;
  const container = document.getElementById("trip-header-container");
  container.innerHTML = "";

  const viewPane = buildTripHeaderViewPane();
  const editPane = buildTripHeaderEditPane();
  const header = Global.el("div", { class: "trip-header" }, [viewPane, editPane]);
  wireViewEditToggle(viewPane, editPane);
  container.appendChild(header);
  applyIcons(container);
}

function buildTripHeaderViewPane() {
  const pane = Global.el("div", { class: "view-pane" });

  const top = Global.el("div", { class: "trip-header-top" });
  const badges = Global.el("div", {});
  if (currentTrip.archived) badges.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));
  top.appendChild(badges);

  const archiveBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: currentTrip.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      currentTrip = await Global.fetchJSON(`${TRIPS_API}/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !currentTrip.archived }),
      });
      Global.showMessage(currentTrip.archived ? "Trip archived." : "Trip unarchived.", "success");
      renderTripHeader();
    },
  });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete trip",
    onclick: async () => {
      const deleted = await confirmAndDeleteTrip(currentTrip);
      if (deleted) window.location.href = "/";
    },
  });

  const agendaLink = Global.el("a", { href: `agenda.html?id=${tripId}`, class: "secondary-btn" }, [
    Global.el("span", { class: "btn-icon", "data-icon": "calendar", "aria-hidden": "true" }),
    " Agenda",
  ]);
  // A plain download link, not a fetch+blob dance - the browser's normal
  // download flow already does the right thing here, and this way it
  // still works as a real link (open in new tab, etc.) if anyone wants
  // that. See app/export.py for what actually gets generated.
  const exportLink = Global.el("a", { href: `${TRIPS_API}/${tripId}/export.xlsx`, class: "secondary-btn", download: "" }, [
    Global.el("span", { class: "btn-icon", "data-icon": "download", "aria-hidden": "true" }),
    " Export",
  ]);
  const editBtn = Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" });
  const actionBtns = [agendaLink, exportLink];
  // Only once the trip has a city to fill from - the endpoint 400s
  // otherwise, and there'd be nothing meaningful for the button to do yet.
  if (currentTrip.city) {
    actionBtns.push(
      Global.el("button", {
        type: "button",
        class: "secondary-btn",
        text: "Fill missing activity cities",
        title: `Sets city to "${currentTrip.city}" on every activity in this trip that doesn't have one yet`,
        onclick: async () => {
          try {
            const { updated } = await Global.fetchJSON(`${TRIPS_API}/${tripId}/fill-missing-cities`, { method: "POST" });
            Global.showMessage(
              updated > 0 ? `Filled city for ${updated} activit${updated === 1 ? "y" : "ies"}.` : "Nothing to fill - every activity already has a city.",
              "success"
            );
            if (updated > 0) loadActivities();
          } catch (err) {
            Global.showMessage(err.message, "error");
          }
        },
      })
    );
  }
  actionBtns.push(archiveBtn, editBtn, deleteBtn);
  top.appendChild(Global.el("div", { class: "trip-header-actions" }, actionBtns));
  pane.appendChild(top);

  const dateLabel = formatDateRange(currentTrip.start_date, currentTrip.end_date);
  const fields = [
    viewField("Location", currentTrip.location),
    viewField("City", currentTrip.city),
    viewField("Dates", dateLabel || "Not set"),
  ].filter(Boolean);
  pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  return pane;
}

function buildTripHeaderEditPane() {
  const pane = Global.el("div", { class: "edit-pane" });

  const locationInput = Global.el("input", { type: "text", value: currentTrip.location, required: "required" });
  const cityInput = cityInputElement(currentTrip.city);
  const startInput = Global.el("input", { type: "date", value: Global.toISODate(currentTrip.start_date) });
  const endInput = Global.el("input", { type: "date", value: Global.toISODate(currentTrip.end_date) });

  pane.appendChild(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Location" }), locationInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "City" }), cityInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date" }), endInput]),
    ])
  );

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => renderTripHeader(),
  });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save trip",
    onclick: async () => {
      const loc = locationInput.value.trim();
      if (!loc) {
        Global.showMessage("Location is required.", "error");
        return;
      }
      try {
        currentTrip = await Global.fetchJSON(`${TRIPS_API}/${tripId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: loc,
            city: cityInput.value.trim() || null,
            start_date: Global.dateInputToISO(startInput.value),
            end_date: Global.dateInputToISO(endInput.value),
          }),
        });
        Global.showMessage("Trip saved.", "success");
        loadCitiesCache(); // fire-and-forget - same reasoning as activity-shared.js's saves
        renderTripHeader();
        loadCoverage();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  pane.appendChild(Global.el("div", { class: "item-actions" }, [cancelBtn, saveBtn]));
  return pane;
}

// --- stay coverage -----------------------------------------------------------

async function loadCoverage() {
  const container = document.getElementById("coverage-banner-container");
  container.innerHTML = "";
  const coverage = await Global.fetchJSON(`${TRIPS_API}/${tripId}/stay-coverage`);
  if (!coverage.has_dates) return;

  if (coverage.covered) {
    container.appendChild(Global.el("div", { class: "coverage-banner covered", text: "✓ Every day of this trip is covered by a stay." }));
    return;
  }

  const banner = Global.el("div", { class: "coverage-banner missing" });
  const n = coverage.missing_dates.length;
  banner.appendChild(document.createTextNode(`⚠ ${n} day${n === 1 ? "" : "s"} not covered by any stay:`));
  banner.appendChild(Global.el("div", { class: "missing-dates", text: coverage.missing_dates.map(formatDateBadge).join(", ") }));
  container.appendChild(banner);
}

// --- stays -------------------------------------------------------------------

function stayCardElement(stay, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (stay.archived ? " archived" : ""), "data-id": stay.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: stay.name }));

  const dateLabel = formatDateRange(stay.start_date, stay.end_date);
  if (dateLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  if (stay.booked) summary.appendChild(Global.el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
  if (stay.archived) summary.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildStayViewEdit(card, stay));
  return card;
}

function buildStayViewEdit(card, stay) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildStayViewPane(card, stay);
  const editPane = buildStayEditPane(card, stay);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildStayViewPane(card, stay) {
  const pane = Global.el("div", { class: "view-pane" });

  const fields = [viewField("Description", stay.description), viewField("Address", stay.address)].filter(Boolean);
  if (fields.length) pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  const links = Global.el("div", { class: "view-links" });
  if (stay.url) links.appendChild(Global.el("a", { href: stay.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (stay.address) {
    links.appendChild(
      Global.el("a", {
        href: googleMapsSearchUrl(stay.address),
        target: "_blank",
        rel: "noopener noreferrer",
        class: "secondary-btn",
        text: "Open map →",
        onclick: (e) => openGoogleMapsPreferringApp(e, "search", stay.address),
      })
    );
  }
  if (links.children.length) pane.appendChild(links);

  if (stay.url) pane.appendChild(buildStayScrapeSection(stay));

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${stay.name}"? This cannot be undone.`)) return;
      await Global.fetchJSON(`${STAYS_API}/${stay.id}`, { method: "DELETE" });
      Global.showMessage(`Deleted "${stay.name}".`, "success");
      loadStays();
      loadCoverage();
    },
  });

  const archiveBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: stay.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await Global.fetchJSON(`${STAYS_API}/${stay.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !stay.archived }),
      });
      Global.showMessage(updated.archived ? `Archived "${updated.name}".` : `Unarchived "${updated.name}".`, "success");
      loadStays();
      loadCoverage();
    },
  });

  actions.append(deleteBtn, archiveBtn, Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildStayEditPane(card, stay) {
  const pane = Global.el("div", { class: "edit-pane" });

  const nameInput = Global.el("input", { type: "text", value: stay.name, required: "required" });
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = stay.description || "";
  const urlInput = Global.el("input", { type: "url", value: stay.url || "" });
  const addressInput = Global.el("input", { type: "text", value: stay.address || "" });
  const startInput = Global.el("input", { type: "date", value: Global.toISODate(stay.start_date), required: "required" });
  const endInput = Global.el("input", { type: "date", value: Global.toISODate(stay.end_date), required: "required" });
  const bookedInput = Global.el("input", { type: "checkbox" });
  bookedInput.checked = stay.booked;

  pane.append(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date" }), endInput]),
    ]),
    Global.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked (this is the confirmed option)")])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => card.replaceWith(stayCardElement(stay, { expanded: true })),
  });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("Name is required.", "error");
        return;
      }
      if (!startInput.value || !endInput.value) {
        Global.showMessage("Start and end date are both required.", "error");
        return;
      }
      try {
        await Global.fetchJSON(`${STAYS_API}/${stay.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            address: addressInput.value.trim() || null,
            start_date: Global.dateInputToISO(startInput.value),
            end_date: Global.dateInputToISO(endInput.value),
            booked: bookedInput.checked,
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        // Reload the whole list rather than patching this card in place -
        // simplest way to keep sort order (active-before-archived) and the
        // coverage banner in sync with whatever changed.
        loadStays();
        loadCoverage();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function buildStayScrapeSection(stay) {
  const section = Global.el("div", { class: "scrape-section" });
  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: stay.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        await Global.fetchJSON(`${STAYS_API}/${stay.id}/scrape`, { method: "POST" });
        loadStays();
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  // renderScrapePreview lives in activity-shared.js - it only reads the
  // generic scrape_* fields, so it works unchanged for stays too.
  section.appendChild(renderScrapePreview(stay));
  return section;
}

function refreshStayCounts() {
  const activeCount = document.querySelectorAll("#stays-list .item-card").length;
  const archivedCount = document.querySelectorAll("#archived-stays-list .item-card").length;

  document.getElementById("stay-count").textContent = activeCount ? `${activeCount}` : "";
  document.getElementById("stays-empty").hidden = activeCount + archivedCount !== 0;

  const archivedSection = document.getElementById("archived-stays-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-stays-summary-text").textContent =
    `${archivedCount} other option${archivedCount === 1 ? "" : "s"}`;
}

async function loadStays() {
  const activeList = document.getElementById("stays-list");
  const archivedList = document.getElementById("archived-stays-list");
  activeList.innerHTML = "";
  archivedList.innerHTML = "";
  const stays = await Global.fetchJSON(`${TRIPS_API}/${tripId}/stays`);
  for (const stay of stays) {
    (stay.archived ? archivedList : activeList).appendChild(stayCardElement(stay));
  }
  refreshStayCounts();
}

function initAddStayForm() {
  const container = document.getElementById("add-stay-container");
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Stay" });

  const nameInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Hotel Le Marais" });
  const descInput = Global.el("textarea", { rows: "2", placeholder: "Optional notes" });
  const urlInput = Global.el("input", { type: "url", placeholder: "https://airbnb.com/rooms/..." });
  const addressInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const startInput = Global.el("input", { type: "date", required: "required" });
  const endInput = Global.el("input", { type: "date", required: "required" });
  const bookedInput = Global.el("input", { type: "checkbox" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name *" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date *" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date *" }), endInput]),
    ]),
    Global.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked")]),
    Global.el("div", { class: "item-actions" }),
  ]);

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn",
    text: "Cancel",
    onclick: () => {
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
    },
  });
  const submitBtn = Global.el("button", { type: "submit", class: "save-btn", text: "Add stay" });
  form.querySelector(".item-actions").append(cancelBtn, submitBtn);

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    nameInput.focus();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    if (!startInput.value || !endInput.value) {
      Global.showMessage("Start and end date are both required.", "error");
      return;
    }
    try {
      await Global.fetchJSON(STAYS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: descInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          address: addressInput.value.trim() || null,
          start_date: Global.dateInputToISO(startInput.value),
          end_date: Global.dateInputToISO(endInput.value),
          booked: bookedInput.checked,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadStays();
      loadCoverage();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

// --- activities (shared code with activities.html) --------------------------

// Which of the three lists (see partitionActivities in activity-shared.js)
// an activity belongs in, and that list's container element.
function listForActivity(activity) {
  if (activity.archived) return document.getElementById("archived-activities-list");
  if (activity.done) return document.getElementById("done-activities-list");
  return document.getElementById("activities-list");
}

function refreshActivityCounts() {
  const activeCount = document.querySelectorAll("#activities-list .item-card").length;
  const doneCount = document.querySelectorAll("#done-activities-list .item-card").length;
  const archivedCount = document.querySelectorAll("#archived-activities-list .item-card").length;

  document.getElementById("activity-count").textContent = activeCount ? `${activeCount}` : "";
  document.getElementById("activities-empty").hidden = activeCount + doneCount + archivedCount !== 0;

  const doneSection = document.getElementById("done-activities-section");
  doneSection.hidden = doneCount === 0;
  document.getElementById("done-activities-summary-text").textContent = `${doneCount} done`;

  const archivedSection = document.getElementById("archived-activities-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-activities-summary-text").textContent = `${archivedCount} archived`;
}

async function unlinkActivity(activity) {
  await Global.fetchJSON(`${TRIPS_API}/${tripId}/activities/${activity.id}`, { method: "DELETE" });
  Global.showMessage(`Removed "${activity.name}" from this trip.`, "success");
  loadActivities();
  loadUnassociatedOptions();
}

// Removes wherever the card currently is and re-places it based on the
// activity's current done/archived state - so toggling either (the
// Archive button or the done checkbox) moves it into the right list
// immediately, same as activities.js's version of this.
function handleActivityChanged(updated) {
  const oldCard = document.querySelector(`#activities-list .item-card[data-id="${updated.id}"], #done-activities-list .item-card[data-id="${updated.id}"], #archived-activities-list .item-card[data-id="${updated.id}"]`);
  if (oldCard) oldCard.remove();
  placeActivityCard(updated, { expanded: true });
  refreshActivityCounts();
}

function placeActivityCard(activity, opts = {}) {
  const card = activityCardElement(activity, {
    onDeleted: () => {
      refreshActivityCounts();
      loadUnassociatedOptions();
    },
    onUnlink: unlinkActivity,
    onChanged: handleActivityChanged,
    ...opts,
  });
  listForActivity(activity).appendChild(card);
  return card;
}

// Kept around (not just a local inside loadActivities) so the distance
// tool's getActivities() closure (see initDistanceTool in
// activity-shared.js) always reads this trip's current activities,
// without needing to re-mount the tool after every reload.
let tripActivities = [];

async function loadActivities() {
  for (const id of ["activities-list", "done-activities-list", "archived-activities-list"]) {
    document.getElementById(id).innerHTML = "";
  }
  tripActivities = await Global.fetchJSON(`${TRIPS_API}/${tripId}/activities`);
  for (const activity of tripActivities) placeActivityCard(activity);
  refreshActivityCounts();
}

async function loadUnassociatedOptions() {
  const activities = await Global.fetchJSON(`${ACTIVITIES_API}?unassociated=true`);
  unassociatedSelect.innerHTML = "";
  if (activities.length === 0) {
    unassociatedSelect.appendChild(Global.el("option", { value: "", text: "No unassociated activities" }));
    unassociatedSelect.disabled = true;
  } else {
    unassociatedSelect.disabled = false;
    unassociatedSelect.appendChild(Global.el("option", { value: "", text: "Attach an existing activity..." }));
    for (const activity of activities) {
      unassociatedSelect.appendChild(Global.el("option", { value: String(activity.id), text: activity.name }));
    }
  }
}

function initAttachActivityPicker() {
  const container = document.getElementById("attach-activity-container");
  unassociatedSelect = Global.el("select", {});
  const attachBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Attach",
    onclick: async () => {
      const activityId = unassociatedSelect.value;
      if (!activityId) return;
      await Global.fetchJSON(`${TRIPS_API}/${tripId}/activities/${activityId}`, { method: "POST" });
      Global.showMessage("Activity attached to trip.", "success");
      loadActivities();
      loadUnassociatedOptions();
    },
  });
  container.append(unassociatedSelect, attachBtn);
  loadUnassociatedOptions();
}

// --- init ---------------------------------------------------------------------

async function init() {
  if (!tripId) {
    Global.showMessage("No trip specified.", "error");
    return;
  }
  try {
    currentTrip = await Global.fetchJSON(`${TRIPS_API}/${tripId}`);
  } catch (err) {
    Global.showMessage(err.message, "error");
    return;
  }

  renderTripHeader();
  loadCoverage();

  initAddStayForm();
  loadStays();

  // Categories have to be loaded before anything that builds a category
  // <select> (the add form below, and every activity card/edit-pane) -
  // see activities.js's init for the same reasoning.
  await loadCategoriesCache();
  await loadCitiesCache();

  initAttachActivityPicker();
  initAddActivityToggle(document.getElementById("add-activity-container"), {
    tripId,
    tripCity: currentTrip.city,
    onCreated: () => {
      loadActivities();
      loadUnassociatedOptions();
    },
  });
  await loadActivities();
  // A getter, not the array itself - tripActivities gets reassigned (not
  // mutated) on every reload, so the tool always reads whatever's current
  // at rebuild time rather than a one-time snapshot from right now. Scoped
  // to just this trip's own activities, unlike activities.html's instance.
  initDistanceTool("distance-tool-mount", () => tripActivities);
}

init();
