// Trips list / create page (index.html).

function tripCardElement(trip, { expanded = false } = {}) {
  const card = el("div", { class: "item-card" + (expanded ? " expanded" : "") + (trip.archived ? " archived" : ""), "data-id": trip.id });

  const summary = el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(el("span", { class: "item-summary-title", text: trip.location }));

  const dateLabel = formatDateRange(trip.start_date, trip.end_date);
  if (dateLabel) summary.appendChild(el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  if (trip.archived) summary.appendChild(el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  summary.appendChild(el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildTripViewEdit(card, trip));
  return card;
}

function buildTripViewEdit(card, trip) {
  const wrap = el("div", { class: "item-details-inner" });
  const viewPane = buildTripViewPane(card, trip);
  const editPane = buildTripEditPane(card, trip);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildTripViewPane(card, trip) {
  const pane = el("div", { class: "view-pane" });

  const dateLabel = formatDateRange(trip.start_date, trip.end_date);
  const fields = [viewField("Location", trip.location), viewField("Dates", dateLabel || "Not set")].filter(Boolean);
  pane.appendChild(el("div", { class: "view-fields" }, fields));

  pane.appendChild(
    el("div", { class: "view-links" }, [
      el("a", { href: `trip.html?id=${trip.id}`, class: "secondary-btn", text: "Open trip page →" }),
    ])
  );

  const actions = el("div", { class: "item-actions" });

  const deleteBtn = el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      const deleted = await confirmAndDeleteTrip(trip);
      if (deleted) {
        card.remove();
        showMessage(`Deleted "${trip.location}".`, "success");
        refreshCounts();
      }
    },
  });

  const archiveBtn = el("button", {
    type: "button",
    class: "secondary-btn",
    text: trip.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await fetchJSON(`${TRIPS_API}/${trip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !trip.archived }),
      });
      showMessage(updated.archived ? `Archived "${updated.location}".` : `Unarchived "${updated.location}".`, "success");
      card.remove();
      placeTripCard(updated);
      refreshCounts();
    },
  });

  actions.append(deleteBtn, archiveBtn, el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildTripEditPane(card, trip) {
  const pane = el("div", { class: "edit-pane" });

  const locationInput = el("input", { type: "text", value: trip.location, required: "required" });
  const startInput = el("input", { type: "date", value: toISODate(trip.start_date) });
  const endInput = el("input", { type: "date", value: toISODate(trip.end_date) });

  pane.appendChild(
    el("div", { class: "item-fields" }, [
      el("div", { class: "field" }, [el("label", { text: "Location" }), locationInput]),
      el("div", { class: "field" }, [el("label", { text: "Start date" }), startInput]),
      el("div", { class: "field" }, [el("label", { text: "End date" }), endInput]),
    ])
  );

  const actions = el("div", { class: "item-actions" });

  const cancelBtn = el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => {
      card.replaceWith(tripCardElement(trip, { expanded: true }));
    },
  });

  const saveBtn = el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const location = locationInput.value.trim();
      if (!location) {
        showMessage("Location is required.", "error");
        return;
      }
      try {
        const updated = await fetchJSON(`${TRIPS_API}/${trip.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location,
            start_date: dateInputToISO(startInput.value),
            end_date: dateInputToISO(endInput.value),
          }),
        });
        showMessage(`Saved "${location}".`, "success");
        card.remove();
        placeTripCard(updated, { expanded: true });
      } catch (err) {
        showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function placeTripCard(trip, opts = {}) {
  const list = trip.archived ? document.getElementById("archived-trips-list") : document.getElementById("trips-list");
  list.appendChild(tripCardElement(trip, opts));
}

function refreshCounts() {
  const activeCount = document.querySelectorAll("#trips-list .item-card").length;
  const archivedCount = document.querySelectorAll("#archived-trips-list .item-card").length;

  document.getElementById("trip-count").textContent = activeCount ? `${activeCount}` : "";
  document.getElementById("empty-state").hidden = activeCount !== 0;

  const archivedSection = document.getElementById("archived-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-summary-text").textContent =
    `${archivedCount} archived trip${archivedCount === 1 ? "" : "s"}`;
}

async function loadTrips() {
  const trips = await fetchJSON(TRIPS_API);
  const tripsList = document.getElementById("trips-list");
  const archivedList = document.getElementById("archived-trips-list");
  tripsList.innerHTML = "";
  archivedList.innerHTML = "";
  for (const trip of trips) placeTripCard(trip);
  refreshCounts();
}

function initAddTripForm() {
  const container = document.getElementById("add-trip-container");
  const showBtn = el("button", { type: "button", class: "add-toggle", text: "+ Add Trip" });

  const locationInput = el("input", { type: "text", required: "required", placeholder: "e.g. Paris, France" });
  const startInput = el("input", { type: "date" });
  const endInput = el("input", { type: "date" });

  const form = el("form", { class: "add-card hidden" }, [
    el("div", { class: "field" }, [el("label", { text: "Location *" }), locationInput]),
    el("div", { class: "field-row" }, [
      el("div", { class: "field" }, [el("label", { text: "Start date" }), startInput]),
      el("div", { class: "field" }, [el("label", { text: "End date" }), endInput]),
    ]),
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
  const submitBtn = el("button", { type: "submit", class: "save-btn", text: "Add trip" });
  form.querySelector(".item-actions").append(cancelBtn, submitBtn);

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    locationInput.focus();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const location = locationInput.value.trim();
    if (!location) return;
    try {
      const created = await fetchJSON(TRIPS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location,
          start_date: dateInputToISO(startInput.value),
          end_date: dateInputToISO(endInput.value),
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      showMessage(`Added "${location}".`, "success");
      placeTripCard(created, { expanded: true });
      refreshCounts();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

initAddTripForm();
loadTrips().catch((err) => showMessage(err.message, "error"));
