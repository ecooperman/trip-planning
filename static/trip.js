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

// --- date-range coverage (stays, dog care - both answer the same "is
// every day away accounted for" question, against DateRangeCoverage's one
// shared shape on the backend - see schemas.DateRangeCoverage) -----------

async function loadCoverageBanner(containerId, endpoint, { coveredText, missingLabel }) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const coverage = await Global.fetchJSON(endpoint);
  if (!coverage.has_dates) return;

  if (coverage.covered) {
    container.appendChild(Global.el("div", { class: "coverage-banner covered", text: `✓ ${coveredText}` }));
    return;
  }

  const banner = Global.el("div", { class: "coverage-banner missing" });
  const n = coverage.missing_dates.length;
  banner.appendChild(document.createTextNode(`⚠ ${n} day${n === 1 ? "" : "s"} ${missingLabel}:`));
  banner.appendChild(Global.el("div", { class: "missing-dates", text: coverage.missing_dates.map(Global.formatDateBadge).join(", ") }));
  container.appendChild(banner);
}

function loadCoverage() {
  return loadCoverageBanner("coverage-banner-container", `${TRIPS_API}/${tripId}/stay-coverage`, {
    coveredText: "Every day of this trip is covered by a stay.",
    missingLabel: "not covered by any stay",
  });
}

function loadDogCareCoverage() {
  return loadCoverageBanner("dog-care-coverage-banner-container", `${TRIPS_API}/${tripId}/dog-care-coverage`, {
    coveredText: "Every day of this trip has dog care arranged.",
    missingLabel: "without dog care arranged",
  });
}

// --- stays -------------------------------------------------------------------

function stayCardElement(stay, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (stay.archived ? " archived" : ""), "data-id": stay.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: stay.name }));

  const dateLabel = formatDateRange(stay.start_date, stay.end_date);
  if (dateLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  const costLabel = formatCost(stay.cost);
  if (costLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-cost", text: costLabel }));
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

  const fields = [
    viewField("Description", stay.description),
    viewField("Address", stay.address),
    viewField("Cost", formatCost(stay.cost)),
  ].filter(Boolean);
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
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", value: stay.cost ?? "" });
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
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
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
            cost: costInput.value.trim() === "" ? null : Number(costInput.value),
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

let tripStays = [];

async function loadStays() {
  const activeList = document.getElementById("stays-list");
  const archivedList = document.getElementById("archived-stays-list");
  activeList.innerHTML = "";
  archivedList.innerHTML = "";
  tripStays = await Global.fetchJSON(`${TRIPS_API}/${tripId}/stays`);
  for (const stay of tripStays) {
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
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const startInput = Global.el("input", { type: "date", required: "required" });
  const endInput = Global.el("input", { type: "date", required: "required" });
  const bookedInput = Global.el("input", { type: "checkbox" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name *" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
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
          cost: costInput.value.trim() === "" ? null : Number(costInput.value),
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

// --- travel (flights, trains, rental cars, ferries) -------------------------

const TRAVEL_API = `${API_BASE}/travel`;

const TRAVEL_TYPE_LABELS = { flight: "Flight", train: "Train", rental_car: "Rental Car", ferry: "Ferry", other: "Other" };

function travelSegmentCardElement(segment, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (segment.archived ? " archived" : ""), "data-id": segment.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: segment.name }));
  summary.appendChild(Global.el("span", { class: "item-badge", text: TRAVEL_TYPE_LABELS[segment.type] || segment.type }));

  const scheduleLabel = formatScheduleBadge(segment.departure_time, segment.arrival_time);
  if (scheduleLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: scheduleLabel }));
  const costLabel = formatCost(segment.cost);
  if (costLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-cost", text: costLabel }));
  if (segment.booked) summary.appendChild(Global.el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
  if (segment.archived) summary.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildTravelSegmentViewEdit(card, segment));
  return card;
}

function buildTravelSegmentViewEdit(card, segment) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildTravelSegmentViewPane(card, segment);
  const editPane = buildTravelSegmentEditPane(card, segment);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildTravelSegmentViewPane(card, segment) {
  const pane = Global.el("div", { class: "view-pane" });

  const route = [segment.departure_location, segment.arrival_location].filter(Boolean).join(" → ") || null;
  const carrierNumber = [segment.carrier, segment.number].filter(Boolean).join(" ") || null;
  const fields = [
    viewField("Route", route),
    viewField("Carrier", carrierNumber),
    viewField("Confirmation #", segment.confirmation_number),
    viewField("Cost", formatCost(segment.cost)),
    viewField("Notes", segment.notes),
  ].filter(Boolean);
  if (fields.length) pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  const links = Global.el("div", { class: "view-links" });
  if (segment.url) links.appendChild(Global.el("a", { href: segment.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (links.children.length) pane.appendChild(links);

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${segment.name}"? This cannot be undone.`)) return;
      await Global.fetchJSON(`${TRAVEL_API}/${segment.id}`, { method: "DELETE" });
      Global.showMessage(`Deleted "${segment.name}".`, "success");
      loadTravelSegments();
    },
  });

  const archiveBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: segment.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await Global.fetchJSON(`${TRAVEL_API}/${segment.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !segment.archived }),
      });
      Global.showMessage(updated.archived ? `Archived "${updated.name}".` : `Unarchived "${updated.name}".`, "success");
      loadTravelSegments();
    },
  });

  actions.append(deleteBtn, archiveBtn, Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function travelSegmentTypeSelect(value) {
  const select = Global.el(
    "select",
    {},
    Object.entries(TRAVEL_TYPE_LABELS).map(([v, label]) => Global.el("option", { value: v, text: label }))
  );
  select.value = value;
  return select;
}

function buildTravelSegmentEditPane(card, segment) {
  const pane = Global.el("div", { class: "edit-pane" });

  const typeInput = travelSegmentTypeSelect(segment.type);
  const nameInput = Global.el("input", { type: "text", value: segment.name, required: "required" });
  const carrierInput = Global.el("input", { type: "text", value: segment.carrier || "" });
  const numberInput = Global.el("input", { type: "text", value: segment.number || "" });
  const departureLocationInput = Global.el("input", { type: "text", value: segment.departure_location || "" });
  const arrivalLocationInput = Global.el("input", { type: "text", value: segment.arrival_location || "" });
  const departureTimeInput = Global.el("input", { type: "datetime-local", value: toDatetimeLocal(segment.departure_time) });
  const arrivalTimeInput = Global.el("input", { type: "datetime-local", value: toDatetimeLocal(segment.arrival_time) });
  const confirmationInput = Global.el("input", { type: "text", value: segment.confirmation_number || "" });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", value: segment.cost ?? "" });
  const urlInput = Global.el("input", { type: "url", value: segment.url || "" });
  const notesInput = Global.el("textarea", { rows: "2" });
  notesInput.value = segment.notes || "";
  const bookedInput = Global.el("input", { type: "checkbox" });
  bookedInput.checked = segment.booked;

  pane.append(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Type" }), typeInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
      Global.el("div", { class: "field-row" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Carrier" }), carrierInput]),
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Number" }), numberInput]),
      ]),
      Global.el("div", { class: "field-row" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Departure location" }), departureLocationInput]),
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Arrival location" }), arrivalLocationInput]),
      ]),
      Global.el("div", { class: "field-row" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Departure time" }), departureTimeInput]),
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Arrival time" }), arrivalTimeInput]),
      ]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Confirmation #" }), confirmationInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Notes" }), notesInput]),
    ]),
    Global.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked (this is the confirmed option)")])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => card.replaceWith(travelSegmentCardElement(segment, { expanded: true })),
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
      try {
        await Global.fetchJSON(`${TRAVEL_API}/${segment.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: typeInput.value,
            name,
            carrier: carrierInput.value.trim() || null,
            number: numberInput.value.trim() || null,
            departure_location: departureLocationInput.value.trim() || null,
            arrival_location: arrivalLocationInput.value.trim() || null,
            departure_time: datetimeLocalToISO(departureTimeInput.value),
            arrival_time: datetimeLocalToISO(arrivalTimeInput.value),
            confirmation_number: confirmationInput.value.trim() || null,
            cost: costInput.value.trim() === "" ? null : Number(costInput.value),
            url: urlInput.value.trim() || null,
            notes: notesInput.value.trim() || null,
            booked: bookedInput.checked,
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        loadTravelSegments();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function refreshTravelCounts() {
  const activeCount = document.querySelectorAll("#travel-list .item-card").length;
  const archivedCount = document.querySelectorAll("#archived-travel-list .item-card").length;

  document.getElementById("travel-count").textContent = activeCount ? `${activeCount}` : "";
  document.getElementById("travel-empty").hidden = activeCount + archivedCount !== 0;

  const archivedSection = document.getElementById("archived-travel-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-travel-summary-text").textContent =
    `${archivedCount} other option${archivedCount === 1 ? "" : "s"}`;
}

let tripTravelSegments = [];

async function loadTravelSegments() {
  const activeList = document.getElementById("travel-list");
  const archivedList = document.getElementById("archived-travel-list");
  activeList.innerHTML = "";
  archivedList.innerHTML = "";
  tripTravelSegments = await Global.fetchJSON(`${TRIPS_API}/${tripId}/travel`);
  for (const segment of tripTravelSegments) {
    (segment.archived ? archivedList : activeList).appendChild(travelSegmentCardElement(segment));
  }
  refreshTravelCounts();
}

function initAddTravelSegmentForm() {
  const container = document.getElementById("add-travel-container");
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Travel" });

  const typeInput = travelSegmentTypeSelect("flight");
  const nameInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Delta 1234 to Toronto" });
  const carrierInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const numberInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const departureLocationInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const arrivalLocationInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const departureTimeInput = Global.el("input", { type: "datetime-local" });
  const arrivalTimeInput = Global.el("input", { type: "datetime-local" });
  const confirmationInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const urlInput = Global.el("input", { type: "url", placeholder: "https://..." });
  const notesInput = Global.el("textarea", { rows: "2", placeholder: "Optional notes" });
  const bookedInput = Global.el("input", { type: "checkbox" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Type" }), typeInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name *" }), nameInput]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Carrier" }), carrierInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Number" }), numberInput]),
    ]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Departure location" }), departureLocationInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Arrival location" }), arrivalLocationInput]),
    ]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Departure time" }), departureTimeInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Arrival time" }), arrivalTimeInput]),
    ]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Confirmation #" }), confirmationInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Notes" }), notesInput]),
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
  const submitBtn = Global.el("button", { type: "submit", class: "save-btn", text: "Add travel" });
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
    try {
      await Global.fetchJSON(TRAVEL_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: typeInput.value,
          name,
          carrier: carrierInput.value.trim() || null,
          number: numberInput.value.trim() || null,
          departure_location: departureLocationInput.value.trim() || null,
          arrival_location: arrivalLocationInput.value.trim() || null,
          departure_time: datetimeLocalToISO(departureTimeInput.value),
          arrival_time: datetimeLocalToISO(arrivalTimeInput.value),
          confirmation_number: confirmationInput.value.trim() || null,
          cost: costInput.value.trim() === "" ? null : Number(costInput.value),
          url: urlInput.value.trim() || null,
          notes: notesInput.value.trim() || null,
          booked: bookedInput.checked,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadTravelSegments();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

// --- dog care (a company or private walker - boarding/sitting/walking) ------

const DOG_CARE_API = `${API_BASE}/dog-care`;

// Same day-arithmetic caution as the datetime helpers up top (common.js) -
// a date-only <input> gives a plain "YYYY-MM-DD" string, and `new
// Date("2026-09-01")` parses that as UTC midnight, which can print back as
// Aug 31 in a negative-UTC-offset timezone. Building the Date from its y/m/d
// parts directly (not from the ISO string) avoids that entirely, the same
// way parseDateTimeParts/partsToDate do for the timed variant.
function addOneDayToDateInput(value) {
  if (!value) return "";
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(y, m - 1, d + 1);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Wires the "choosing a start date sets the end date to the day after"
// convenience onto a start/end date input pair - shared by the add form
// and the edit pane below.
function wireDogCareDateDefaulting(startInput, endInput) {
  startInput.addEventListener("change", () => {
    endInput.value = addOneDayToDateInput(startInput.value);
  });
}

// One of the two optional file attachments (invoice / instructions) - a
// download link + Remove once uploaded, or a file picker + Upload button
// before that. Deliberately dumb: no preview, no parsing, just bytes in
// and bytes back out (see models.DogCareBooking's docstring on why - a
// public no-login link for instructions specifically is a real, deferred
// follow-up, not built here; both are private downloads today, gated the
// same as every other route in this app via Cloudflare Access).
function buildDogCareAttachmentField(booking, kind, label, onChanged) {
  const wrap = Global.el("div", { class: "field" });
  wrap.appendChild(Global.el("label", { text: label }));
  const controls = Global.el("div", { class: "attachment-controls" });
  const filename = booking[`${kind}_filename`];

  if (filename) {
    controls.append(
      Global.el("a", {
        href: `${DOG_CARE_API}/${booking.id}/attachments/${kind}`,
        target: "_blank",
        rel: "noopener noreferrer",
        class: "secondary-btn",
        text: `Download (${filename})`,
      }),
      Global.el("button", {
        type: "button",
        class: "danger-btn",
        text: "Remove",
        onclick: async () => {
          if (!confirm(`Remove the ${label.toLowerCase()}?`)) return;
          await Global.fetchJSON(`${DOG_CARE_API}/${booking.id}/attachments/${kind}`, { method: "DELETE" });
          Global.showMessage(`Removed ${label.toLowerCase()}.`, "success");
          onChanged();
        },
      })
    );
  } else {
    const fileInput = Global.el("input", { type: "file", accept: "application/pdf" });
    controls.append(
      fileInput,
      Global.el("button", {
        type: "button",
        class: "secondary-btn",
        text: "Upload",
        onclick: async () => {
          const file = fileInput.files[0];
          if (!file) {
            Global.showMessage("Choose a file first.", "error");
            return;
          }
          const body = new FormData();
          body.append("file", file);
          try {
            // A plain FormData body - Global.fetchJSON passes options
            // straight to fetch() without forcing a Content-Type, so the
            // browser sets the correct multipart boundary itself. This is
            // the one call in this file that relies on that pass-through
            // instead of setting its own "Content-Type: application/json"
            // header the way every other call here does.
            await Global.fetchJSON(`${DOG_CARE_API}/${booking.id}/attachments/${kind}`, { method: "POST", body });
            Global.showMessage(`Uploaded ${label.toLowerCase()}.`, "success");
            onChanged();
          } catch (err) {
            Global.showMessage(err.message, "error");
          }
        },
      })
    );
  }
  wrap.appendChild(controls);
  return wrap;
}

function dogCareBookingCardElement(booking, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (booking.archived ? " archived" : ""), "data-id": booking.id });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: booking.company_name }));

  const dateLabel = formatDateRange(booking.start_date, booking.end_date);
  if (dateLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  const costLabel = formatCost(booking.cost);
  if (costLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-cost", text: costLabel }));
  if (booking.booked) summary.appendChild(Global.el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
  if (booking.archived) summary.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildDogCareBookingViewEdit(card, booking));
  return card;
}

function buildDogCareBookingViewEdit(card, booking) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildDogCareBookingViewPane(card, booking);
  const editPane = buildDogCareBookingEditPane(card, booking);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildDogCareBookingViewPane(card, booking) {
  const pane = Global.el("div", { class: "view-pane" });

  const fields = [
    viewField("Walker", booking.walker_name),
    viewField("Cost", formatCost(booking.cost)),
  ].filter(Boolean);
  if (fields.length) pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  const links = Global.el("div", { class: "view-links" });
  if (booking.url) links.appendChild(Global.el("a", { href: booking.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (links.children.length) pane.appendChild(links);

  const reload = () => loadDogCareBookings();
  pane.append(
    buildDogCareAttachmentField(booking, "invoice", "Invoice", reload),
    buildDogCareAttachmentField(booking, "instructions", "Instructions", reload)
  );

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${booking.company_name}"? This cannot be undone.`)) return;
      await Global.fetchJSON(`${DOG_CARE_API}/${booking.id}`, { method: "DELETE" });
      Global.showMessage(`Deleted "${booking.company_name}".`, "success");
      loadDogCareBookings();
      loadDogCareCoverage();
    },
  });

  const archiveBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: booking.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await Global.fetchJSON(`${DOG_CARE_API}/${booking.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !booking.archived }),
      });
      Global.showMessage(updated.archived ? `Archived "${updated.company_name}".` : `Unarchived "${updated.company_name}".`, "success");
      loadDogCareBookings();
      loadDogCareCoverage();
    },
  });

  actions.append(deleteBtn, archiveBtn, Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildDogCareBookingEditPane(card, booking) {
  const pane = Global.el("div", { class: "edit-pane" });

  const companyInput = Global.el("input", { type: "text", value: booking.company_name, required: "required" });
  const walkerInput = Global.el("input", { type: "text", value: booking.walker_name || "" });
  const urlInput = Global.el("input", { type: "url", value: booking.url || "" });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", value: booking.cost ?? "" });
  const startInput = Global.el("input", { type: "date", value: Global.toISODate(booking.start_date), required: "required" });
  const endInput = Global.el("input", { type: "date", value: Global.toISODate(booking.end_date), required: "required" });
  wireDogCareDateDefaulting(startInput, endInput);
  const bookedInput = Global.el("input", { type: "checkbox" });
  bookedInput.checked = booking.booked;

  pane.append(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Company" }), companyInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Walker" }), walkerInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
      Global.el("div", { class: "field-row" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date" }), startInput]),
        Global.el("div", { class: "field" }, [Global.el("label", { text: "End date" }), endInput]),
      ]),
    ]),
    Global.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked (this is the confirmed option)")])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => card.replaceWith(dogCareBookingCardElement(booking, { expanded: true })),
  });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const companyName = companyInput.value.trim();
      if (!companyName) {
        Global.showMessage("Company name is required.", "error");
        return;
      }
      if (!startInput.value || !endInput.value) {
        Global.showMessage("Start and end date are both required.", "error");
        return;
      }
      try {
        await Global.fetchJSON(`${DOG_CARE_API}/${booking.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_name: companyName,
            walker_name: walkerInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            cost: costInput.value.trim() === "" ? null : Number(costInput.value),
            start_date: Global.dateInputToISO(startInput.value),
            end_date: Global.dateInputToISO(endInput.value),
            booked: bookedInput.checked,
          }),
        });
        Global.showMessage(`Saved "${companyName}".`, "success");
        loadDogCareBookings();
        loadDogCareCoverage();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function refreshDogCareCounts() {
  const activeCount = document.querySelectorAll("#dog-care-list .item-card").length;
  const archivedCount = document.querySelectorAll("#archived-dog-care-list .item-card").length;

  document.getElementById("dog-care-count").textContent = activeCount ? `${activeCount}` : "";
  document.getElementById("dog-care-empty").hidden = activeCount + archivedCount !== 0;

  const archivedSection = document.getElementById("archived-dog-care-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-dog-care-summary-text").textContent =
    `${archivedCount} other option${archivedCount === 1 ? "" : "s"}`;
}

async function loadDogCareBookings() {
  const activeList = document.getElementById("dog-care-list");
  const archivedList = document.getElementById("archived-dog-care-list");
  activeList.innerHTML = "";
  archivedList.innerHTML = "";
  const bookings = await Global.fetchJSON(`${TRIPS_API}/${tripId}/dog-care`);
  for (const booking of bookings) {
    (booking.archived ? archivedList : activeList).appendChild(dogCareBookingCardElement(booking));
  }
  refreshDogCareCounts();
}

function initAddDogCareForm() {
  const container = document.getElementById("add-dog-care-container");
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Dog Care" });

  const companyInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Green Paws Chicago" });
  const walkerInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const urlInput = Global.el("input", { type: "url", placeholder: "https://..." });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const startInput = Global.el("input", { type: "date", required: "required" });
  const endInput = Global.el("input", { type: "date", required: "required" });
  wireDogCareDateDefaulting(startInput, endInput);
  const bookedInput = Global.el("input", { type: "checkbox" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Company *" }), companyInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Walker" }), walkerInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date *" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date *" }), endInput]),
    ]),
    Global.el("label", { class: "checkbox-label" }, [bookedInput, document.createTextNode("Booked")]),
    Global.el("p", { class: "note", text: "Add invoice/instructions PDFs after saving - attachments live on the card below once it's created." }),
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
  const submitBtn = Global.el("button", { type: "submit", class: "save-btn", text: "Add dog care" });
  form.querySelector(".item-actions").append(cancelBtn, submitBtn);

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    companyInput.focus();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const companyName = companyInput.value.trim();
    if (!companyName) return;
    if (!startInput.value || !endInput.value) {
      Global.showMessage("Start and end date are both required.", "error");
      return;
    }
    try {
      await Global.fetchJSON(DOG_CARE_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: companyName,
          walker_name: walkerInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          cost: costInput.value.trim() === "" ? null : Number(costInput.value),
          start_date: Global.dateInputToISO(startInput.value),
          end_date: Global.dateInputToISO(endInput.value),
          booked: bookedInput.checked,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${companyName}".`, "success");
      loadDogCareBookings();
      loadDogCareCoverage();
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

  initAddTravelSegmentForm();
  loadTravelSegments();

  initAddDogCareForm();
  loadDogCareBookings();
  loadDogCareCoverage();

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
  // Getters, not the arrays themselves - tripActivities/tripStays get
  // reassigned (not mutated) on every reload, so the tool always reads
  // whatever's current at rebuild time rather than a one-time snapshot
  // from right now. Scoped to just this trip's own activities and stays,
  // unlike activities.html's instance (which has no single trip to scope
  // stays to, so it only ever offers activities - see initDistanceTool).
  initDistanceTool("distance-tool-mount", () => tripActivities, () => tripStays);
}

init();
