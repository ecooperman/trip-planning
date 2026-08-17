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
  const header = Theme.el("div", { class: "trip-header" }, [viewPane, editPane]);
  wireViewEditToggle(viewPane, editPane);
  container.appendChild(header);
  applyIcons(container);
}

function buildTripHeaderViewPane() {
  const pane = Theme.el("div", { class: "view-pane" });

  const top = Theme.el("div", { class: "trip-header-top" });
  const badges = Theme.el("div", {});
  if (currentTrip.archived) badges.appendChild(Theme.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));
  top.appendChild(badges);

  const archiveBtn = Theme.el("button", {
    type: "button",
    class: "secondary-btn",
    text: currentTrip.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      currentTrip = await fetchJSON(`${TRIPS_API}/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !currentTrip.archived }),
      });
      Theme.showMessage(currentTrip.archived ? "Trip archived." : "Trip unarchived.", "success");
      renderTripHeader();
    },
  });

  const deleteBtn = Theme.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete trip",
    onclick: async () => {
      const deleted = await confirmAndDeleteTrip(currentTrip);
      if (deleted) window.location.href = "/";
    },
  });

  const agendaLink = Theme.el("a", { href: `agenda.html?id=${tripId}`, class: "secondary-btn" }, [
    Theme.el("span", { class: "btn-icon", "data-icon": "calendar", "aria-hidden": "true" }),
    " Agenda",
  ]);
  const editBtn = Theme.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" });
  top.appendChild(Theme.el("div", { class: "trip-header-actions" }, [agendaLink, archiveBtn, editBtn, deleteBtn]));
  pane.appendChild(top);

  const dateLabel = formatDateRange(currentTrip.start_date, currentTrip.end_date);
  const fields = [viewField("Location", currentTrip.location), viewField("Dates", dateLabel || "Not set")].filter(Boolean);
  pane.appendChild(Theme.el("div", { class: "view-fields" }, fields));

  return pane;
}

function buildTripHeaderEditPane() {
  const pane = Theme.el("div", { class: "edit-pane" });

  const locationInput = Theme.el("input", { type: "text", value: currentTrip.location, required: "required" });
  const startInput = Theme.el("input", { type: "date", value: toISODate(currentTrip.start_date) });
  const endInput = Theme.el("input", { type: "date", value: toISODate(currentTrip.end_date) });

  pane.appendChild(
    Theme.el("div", { class: "item-fields" }, [
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Location" }), locationInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Start date" }), startInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "End date" }), endInput]),
    ])
  );

  const cancelBtn = Theme.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => renderTripHeader(),
  });

  const saveBtn = Theme.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save trip",
    onclick: async () => {
      const loc = locationInput.value.trim();
      if (!loc) {
        Theme.showMessage("Location is required.", "error");
        return;
      }
      try {
        currentTrip = await fetchJSON(`${TRIPS_API}/${tripId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: loc,
            start_date: dateInputToISO(startInput.value),
            end_date: dateInputToISO(endInput.value),
          }),
        });
        Theme.showMessage("Trip saved.", "success");
        renderTripHeader();
        loadCoverage();
      } catch (err) {
        Theme.showMessage(err.message, "error");
      }
    },
  });

  pane.appendChild(Theme.el("div", { class: "item-actions" }, [cancelBtn, saveBtn]));
  return pane;
}

// --- stay coverage -----------------------------------------------------------

async function loadCoverage() {
  const container = document.getElementById("coverage-banner-container");
  container.innerHTML = "";
  const coverage = await fetchJSON(`${TRIPS_API}/${tripId}/stay-coverage`);
  if (!coverage.has_dates) return;

  if (coverage.covered) {
    container.appendChild(Theme.el("div", { class: "coverage-banner covered", text: "✓ Every day of this trip is covered by a stay." }));
    return;
  }

  const banner = Theme.el("div", { class: "coverage-banner missing" });
  const n = coverage.missing_dates.length;
  banner.appendChild(document.createTextNode(`⚠ ${n} day${n === 1 ? "" : "s"} not covered by any stay:`));
  banner.appendChild(Theme.el("div", { class: "missing-dates", text: coverage.missing_dates.map(formatDateBadge).join(", ") }));
  container.appendChild(banner);
}

// --- stays -------------------------------------------------------------------

function stayCardElement(stay, { expanded = false } = {}) {
  const card = Theme.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (stay.archived ? " archived" : ""), "data-id": stay.id });

  const summary = Theme.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Theme.el("span", { class: "item-summary-title", text: stay.name }));

  const dateLabel = formatDateRange(stay.start_date, stay.end_date);
  if (dateLabel) summary.appendChild(Theme.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  if (stay.booked) summary.appendChild(Theme.el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
  if (stay.archived) summary.appendChild(Theme.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(Theme.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Theme.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
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
  const wrap = Theme.el("div", { class: "item-details-inner" });
  const viewPane = buildStayViewPane(card, stay);
  const editPane = buildStayEditPane(card, stay);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildStayViewPane(card, stay) {
  const pane = Theme.el("div", { class: "view-pane" });

  const fields = [viewField("Description", stay.description), viewField("Address", stay.address)].filter(Boolean);
  if (fields.length) pane.appendChild(Theme.el("div", { class: "view-fields" }, fields));

  const links = Theme.el("div", { class: "view-links" });
  if (stay.url) links.appendChild(Theme.el("a", { href: stay.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (stay.address) {
    links.appendChild(
      Theme.el("a", {
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

  const actions = Theme.el("div", { class: "item-actions" });

  const deleteBtn = Theme.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${stay.name}"? This cannot be undone.`)) return;
      await fetchJSON(`${STAYS_API}/${stay.id}`, { method: "DELETE" });
      Theme.showMessage(`Deleted "${stay.name}".`, "success");
      loadStays();
      loadCoverage();
    },
  });

  const archiveBtn = Theme.el("button", {
    type: "button",
    class: "secondary-btn",
    text: stay.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await fetchJSON(`${STAYS_API}/${stay.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !stay.archived }),
      });
      Theme.showMessage(updated.archived ? `Archived "${updated.name}".` : `Unarchived "${updated.name}".`, "success");
      loadStays();
      loadCoverage();
    },
  });

  actions.append(deleteBtn, archiveBtn, Theme.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildStayEditPane(card, stay) {
  const pane = Theme.el("div", { class: "edit-pane" });

  const nameInput = Theme.el("input", { type: "text", value: stay.name, required: "required" });
  const descInput = Theme.el("textarea", { rows: "2" });
  descInput.value = stay.description || "";
  const urlInput = Theme.el("input", { type: "url", value: stay.url || "" });
  const addressInput = Theme.el("input", { type: "text", value: stay.address || "" });
  const startInput = Theme.el("input", { type: "date", value: toISODate(stay.start_date), required: "required" });
  const endInput = Theme.el("input", { type: "date", value: toISODate(stay.end_date), required: "required" });
  const bookedInput = Theme.el("input", { type: "checkbox" });
  bookedInput.checked = stay.booked;

  pane.append(
    Theme.el("div", { class: "item-fields" }, [
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Name" }), nameInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Description" }), descInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "URL" }), urlInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Address" }), addressInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Start date" }), startInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "End date" }), endInput]),
    ]),
    Theme.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked (this is the confirmed option)")])
  );

  const actions = Theme.el("div", { class: "item-actions" });

  const cancelBtn = Theme.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => card.replaceWith(stayCardElement(stay, { expanded: true })),
  });

  const saveBtn = Theme.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Theme.showMessage("Name is required.", "error");
        return;
      }
      if (!startInput.value || !endInput.value) {
        Theme.showMessage("Start and end date are both required.", "error");
        return;
      }
      try {
        await fetchJSON(`${STAYS_API}/${stay.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            address: addressInput.value.trim() || null,
            start_date: dateInputToISO(startInput.value),
            end_date: dateInputToISO(endInput.value),
            booked: bookedInput.checked,
          }),
        });
        Theme.showMessage(`Saved "${name}".`, "success");
        // Reload the whole list rather than patching this card in place -
        // simplest way to keep sort order (active-before-archived) and the
        // coverage banner in sync with whatever changed.
        loadStays();
        loadCoverage();
      } catch (err) {
        Theme.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function buildStayScrapeSection(stay) {
  const section = Theme.el("div", { class: "scrape-section" });
  const scrapeBtn = Theme.el("button", {
    type: "button",
    class: "scrape-btn",
    text: stay.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        await fetchJSON(`${STAYS_API}/${stay.id}/scrape`, { method: "POST" });
        loadStays();
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Theme.showMessage(`Preview fetch failed: ${err.message}`, "error");
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
  const stays = await fetchJSON(`${TRIPS_API}/${tripId}/stays`);
  for (const stay of stays) {
    (stay.archived ? archivedList : activeList).appendChild(stayCardElement(stay));
  }
  refreshStayCounts();
}

function initAddStayForm() {
  const container = document.getElementById("add-stay-container");
  const showBtn = Theme.el("button", { type: "button", class: "add-toggle", text: "+ Add Stay" });

  const nameInput = Theme.el("input", { type: "text", required: "required", placeholder: "e.g. Hotel Le Marais" });
  const descInput = Theme.el("textarea", { rows: "2", placeholder: "Optional notes" });
  const urlInput = Theme.el("input", { type: "url", placeholder: "https://airbnb.com/rooms/..." });
  const addressInput = Theme.el("input", { type: "text", placeholder: "Optional" });
  const startInput = Theme.el("input", { type: "date", required: "required" });
  const endInput = Theme.el("input", { type: "date", required: "required" });
  const bookedInput = Theme.el("input", { type: "checkbox" });

  const form = Theme.el("form", { class: "add-card hidden" }, [
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Name *" }), nameInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Description" }), descInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "URL" }), urlInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Address" }), addressInput]),
    Theme.el("div", { class: "field-row" }, [
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Start date *" }), startInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "End date *" }), endInput]),
    ]),
    Theme.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked")]),
    Theme.el("div", { class: "item-actions" }),
  ]);

  const cancelBtn = Theme.el("button", {
    type: "button",
    class: "cancel-btn",
    text: "Cancel",
    onclick: () => {
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
    },
  });
  const submitBtn = Theme.el("button", { type: "submit", class: "save-btn", text: "Add stay" });
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
      Theme.showMessage("Start and end date are both required.", "error");
      return;
    }
    try {
      await fetchJSON(STAYS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: descInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          address: addressInput.value.trim() || null,
          start_date: dateInputToISO(startInput.value),
          end_date: dateInputToISO(endInput.value),
          booked: bookedInput.checked,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Theme.showMessage(`Added "${name}".`, "success");
      loadStays();
      loadCoverage();
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

// --- activities (shared code with activities.html) --------------------------

function refreshActivityCounts() {
  const count = document.querySelectorAll("#activities-list .item-card").length;
  document.getElementById("activity-count").textContent = count ? `${count}` : "";
  document.getElementById("activities-empty").hidden = count !== 0;
}

async function unlinkActivity(activity) {
  await fetchJSON(`${TRIPS_API}/${tripId}/activities/${activity.id}`, { method: "DELETE" });
  Theme.showMessage(`Removed "${activity.name}" from this trip.`, "success");
  loadActivities();
  loadUnassociatedOptions();
}

async function loadActivities() {
  const list = document.getElementById("activities-list");
  list.innerHTML = "";
  const activities = await fetchJSON(`${TRIPS_API}/${tripId}/activities`);
  for (const activity of activities) {
    list.appendChild(
      activityCardElement(activity, {
        onDeleted: () => {
          refreshActivityCounts();
          loadUnassociatedOptions();
        },
        onUnlink: unlinkActivity,
      })
    );
  }
  refreshActivityCounts();
}

async function loadUnassociatedOptions() {
  const activities = await fetchJSON(`${ACTIVITIES_API}?unassociated=true`);
  unassociatedSelect.innerHTML = "";
  if (activities.length === 0) {
    unassociatedSelect.appendChild(Theme.el("option", { value: "", text: "No unassociated activities" }));
    unassociatedSelect.disabled = true;
  } else {
    unassociatedSelect.disabled = false;
    unassociatedSelect.appendChild(Theme.el("option", { value: "", text: "Attach an existing activity..." }));
    for (const activity of activities) {
      unassociatedSelect.appendChild(Theme.el("option", { value: String(activity.id), text: activity.name }));
    }
  }
}

function initAttachActivityPicker() {
  const container = document.getElementById("attach-activity-container");
  unassociatedSelect = Theme.el("select", {});
  const attachBtn = Theme.el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Attach",
    onclick: async () => {
      const activityId = unassociatedSelect.value;
      if (!activityId) return;
      await fetchJSON(`${TRIPS_API}/${tripId}/activities/${activityId}`, { method: "POST" });
      Theme.showMessage("Activity attached to trip.", "success");
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
    Theme.showMessage("No trip specified.", "error");
    return;
  }
  try {
    currentTrip = await fetchJSON(`${TRIPS_API}/${tripId}`);
  } catch (err) {
    Theme.showMessage(err.message, "error");
    return;
  }

  renderTripHeader();
  loadCoverage();

  initAddStayForm();
  loadStays();

  initAttachActivityPicker();
  initAddActivityToggle(document.getElementById("add-activity-container"), {
    tripId,
    onCreated: () => {
      loadActivities();
      loadUnassociatedOptions();
    },
  });
  loadActivities();
}

init();
