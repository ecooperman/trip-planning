// Trip detail page: trip header, stay-coverage banner, stays (inline -
// there's no standalone stays page since a stay always belongs to a trip),
// and activities (via activity-shared.js, the same code as activities.html).

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

  const locationInput = el("input", { type: "text", value: currentTrip.location, required: "required" });
  const startInput = el("input", { type: "date", value: toISODate(currentTrip.start_date) });
  const endInput = el("input", { type: "date", value: toISODate(currentTrip.end_date) });

  const top = el("div", { class: "trip-header-top" });
  const badges = el("div", {});
  if (currentTrip.archived) badges.appendChild(el("span", { class: "item-badge item-badge-archived", text: "Archived" }));
  top.appendChild(badges);

  const archiveBtn = el("button", {
    type: "button",
    class: "secondary-btn",
    text: currentTrip.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      currentTrip = await fetchJSON(`${TRIPS_API}/${tripId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !currentTrip.archived }),
      });
      showMessage(currentTrip.archived ? "Trip archived." : "Trip unarchived.", "success");
      renderTripHeader();
    },
  });

  const deleteBtn = el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete trip",
    onclick: async () => {
      const deleted = await confirmAndDeleteTrip(currentTrip);
      if (deleted) window.location.href = "/";
    },
  });

  top.appendChild(el("div", { class: "trip-header-actions" }, [archiveBtn, deleteBtn]));

  const fields = el("div", { class: "item-fields" }, [
    el("div", { class: "field" }, [el("label", { text: "Location" }), locationInput]),
    el("div", { class: "field" }, [el("label", { text: "Start date" }), startInput]),
    el("div", { class: "field" }, [el("label", { text: "End date" }), endInput]),
  ]);

  const saveBtn = el("button", {
    type: "button",
    class: "save-btn",
    text: "Save trip",
    onclick: async () => {
      const loc = locationInput.value.trim();
      if (!loc) {
        showMessage("Location is required.", "error");
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
        showMessage("Trip saved.", "success");
        renderTripHeader();
        loadCoverage();
      } catch (err) {
        showMessage(err.message, "error");
      }
    },
  });

  const header = el("div", { class: "trip-header" }, [top, fields, el("div", { class: "item-actions" }, [saveBtn])]);
  container.appendChild(header);
}

// --- stay coverage -----------------------------------------------------------

async function loadCoverage() {
  const container = document.getElementById("coverage-banner-container");
  container.innerHTML = "";
  const coverage = await fetchJSON(`${TRIPS_API}/${tripId}/stay-coverage`);
  if (!coverage.has_dates) return;

  if (coverage.covered) {
    container.appendChild(el("div", { class: "coverage-banner covered", text: "✓ Every day of this trip is covered by a stay." }));
    return;
  }

  const banner = el("div", { class: "coverage-banner missing" });
  const n = coverage.missing_dates.length;
  banner.appendChild(document.createTextNode(`⚠ ${n} day${n === 1 ? "" : "s"} not covered by any stay:`));
  banner.appendChild(el("div", { class: "missing-dates", text: coverage.missing_dates.map(formatDateBadge).join(", ") }));
  container.appendChild(banner);
}

// --- stays -------------------------------------------------------------------

function stayCardElement(stay, { expanded = false } = {}) {
  const card = el("div", { class: "item-card" + (expanded ? " expanded" : "") + (stay.archived ? " archived" : ""), "data-id": stay.id });

  const summary = el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(el("span", { class: "item-summary-title", text: stay.name }));

  const dateLabel = formatDateRange(stay.start_date, stay.end_date);
  if (dateLabel) summary.appendChild(el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  if (stay.booked) summary.appendChild(el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
  if (stay.archived) summary.appendChild(el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildStayDetails(card, stay));
  return card;
}

function buildStayDetails(card, stay) {
  const wrap = el("div", { class: "item-details-inner" });

  const nameInput = el("input", { type: "text", value: stay.name, required: "required" });
  const descInput = el("textarea", { rows: "2" });
  descInput.value = stay.description || "";
  const urlInput = el("input", { type: "url", value: stay.url || "" });
  const startInput = el("input", { type: "date", value: toISODate(stay.start_date), required: "required" });
  const endInput = el("input", { type: "date", value: toISODate(stay.end_date), required: "required" });
  const bookedInput = el("input", { type: "checkbox" });
  bookedInput.checked = stay.booked;

  wrap.append(
    el("div", { class: "item-fields" }, [
      el("div", { class: "field" }, [el("label", { text: "Name" }), nameInput]),
      el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]),
      el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]),
      el("div", { class: "field" }, [el("label", { text: "Start date" }), startInput]),
      el("div", { class: "field" }, [el("label", { text: "End date" }), endInput]),
    ]),
    el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked (this is the confirmed option)")])
  );

  if (stay.url) {
    wrap.appendChild(buildStayScrapeSection(stay));
  }

  const actions = el("div", { class: "item-actions" });

  const deleteBtn = el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${stay.name}"? This cannot be undone.`)) return;
      await fetchJSON(`${STAYS_API}/${stay.id}`, { method: "DELETE" });
      showMessage(`Deleted "${stay.name}".`, "success");
      loadStays();
      loadCoverage();
    },
  });

  const saveBtn = el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        showMessage("Name is required.", "error");
        return;
      }
      if (!startInput.value || !endInput.value) {
        showMessage("Start and end date are both required.", "error");
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
            start_date: dateInputToISO(startInput.value),
            end_date: dateInputToISO(endInput.value),
            booked: bookedInput.checked,
          }),
        });
        showMessage(`Saved "${name}".`, "success");
        // Reload the whole list rather than patching this card in place -
        // marking a stay booked can archive its siblings on this trip, and
        // that side effect only shows up by re-fetching.
        loadStays();
        loadCoverage();
      } catch (err) {
        showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildStayScrapeSection(stay) {
  const section = el("div", { class: "scrape-section" });
  const scrapeBtn = el("button", {
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
        showMessage(`Preview fetch failed: ${err.message}`, "error");
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
  const showBtn = el("button", { type: "button", class: "add-toggle", text: "+ Add Stay" });

  const nameInput = el("input", { type: "text", required: "required", placeholder: "e.g. Hotel Le Marais" });
  const descInput = el("textarea", { rows: "2", placeholder: "Optional notes" });
  const urlInput = el("input", { type: "url", placeholder: "https://airbnb.com/rooms/..." });
  const startInput = el("input", { type: "date", required: "required" });
  const endInput = el("input", { type: "date", required: "required" });
  const bookedInput = el("input", { type: "checkbox" });

  const form = el("form", { class: "add-card hidden" }, [
    el("div", { class: "field" }, [el("label", { text: "Name *" }), nameInput]),
    el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]),
    el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]),
    el("div", { class: "field-row" }, [
      el("div", { class: "field" }, [el("label", { text: "Start date *" }), startInput]),
      el("div", { class: "field" }, [el("label", { text: "End date *" }), endInput]),
    ]),
    el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked")]),
    el("div", { class: "item-actions" }),
  ]);

  const cancelBtn = el("button", {
    type: "button",
    class: "cancel-btn",
    text: "Cancel",
    onclick: () => {
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
    },
  });
  const submitBtn = el("button", { type: "submit", class: "save-btn", text: "Add stay" });
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
      showMessage("Start and end date are both required.", "error");
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
          start_date: dateInputToISO(startInput.value),
          end_date: dateInputToISO(endInput.value),
          booked: bookedInput.checked,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      showMessage(`Added "${name}".`, "success");
      loadStays();
      loadCoverage();
    } catch (err) {
      showMessage(err.message, "error");
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
  showMessage(`Removed "${activity.name}" from this trip.`, "success");
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
    unassociatedSelect.appendChild(el("option", { value: "", text: "No unassociated activities" }));
    unassociatedSelect.disabled = true;
  } else {
    unassociatedSelect.disabled = false;
    unassociatedSelect.appendChild(el("option", { value: "", text: "Attach an existing activity..." }));
    for (const activity of activities) {
      unassociatedSelect.appendChild(el("option", { value: String(activity.id), text: activity.name }));
    }
  }
}

function initAttachActivityPicker() {
  const container = document.getElementById("attach-activity-container");
  unassociatedSelect = el("select", {});
  const attachBtn = el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Attach",
    onclick: async () => {
      const activityId = unassociatedSelect.value;
      if (!activityId) return;
      await fetchJSON(`${TRIPS_API}/${tripId}/activities/${activityId}`, { method: "POST" });
      showMessage("Activity attached to trip.", "success");
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
    showMessage("No trip specified.", "error");
    return;
  }
  try {
    currentTrip = await fetchJSON(`${TRIPS_API}/${tripId}`);
  } catch (err) {
    showMessage(err.message, "error");
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
