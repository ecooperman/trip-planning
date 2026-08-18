// Trips list / create page (index.html).

function tripCardElement(trip, { expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (trip.archived ? " archived" : ""), "data-id": trip.id });

  // A <div role="button"> rather than a real <button> - the nested Agenda
  // link below is interactive content, which is invalid (and flaky for
  // keyboard/screen-reader nav) inside a real <button>. tabindex + the
  // keydown handler keep it fully keyboard-operable despite not being a
  // native button.
  const summary = Global.el("div", { class: "item-summary", role: "button", tabindex: "0", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: trip.location }));

  const dateLabel = formatDateRange(trip.start_date, trip.end_date);
  if (dateLabel) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  if (trip.archived) summary.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));

  const agendaLink = Global.el("a", {
    href: `agenda.html?id=${trip.id}`,
    class: "item-summary-icon-link",
    "aria-label": `Open agenda for ${trip.location}`,
  }, [Global.el("span", { class: "btn-icon", "data-icon": "calendar", "aria-hidden": "true" })]);
  agendaLink.addEventListener("click", (e) => e.stopPropagation());
  summary.appendChild(agendaLink);

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  function toggle() {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  }
  summary.addEventListener("click", toggle);
  summary.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  });

  card.append(summary, details);
  details.appendChild(buildTripViewEdit(card, trip));
  return card;
}

function buildTripViewEdit(card, trip) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildTripViewPane(card, trip);
  const editPane = buildTripEditPane(card, trip);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildTripViewPane(card, trip) {
  const pane = Global.el("div", { class: "view-pane" });

  const dateLabel = formatDateRange(trip.start_date, trip.end_date);
  const fields = [viewField("Location", trip.location), viewField("Dates", dateLabel || "Not set")].filter(Boolean);
  pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  pane.appendChild(
    Global.el("div", { class: "view-links" }, [
      Global.el("a", { href: `trip.html?id=${trip.id}`, class: "secondary-btn", text: "Open trip page →" }),
    ])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      const deleted = await confirmAndDeleteTrip(trip);
      if (deleted) {
        card.remove();
        Global.showMessage(`Deleted "${trip.location}".`, "success");
        refreshCounts();
      }
    },
  });

  const archiveBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: trip.archived ? "Unarchive" : "Archive",
    onclick: async () => {
      const updated = await Global.fetchJSON(`${TRIPS_API}/${trip.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !trip.archived }),
      });
      Global.showMessage(updated.archived ? `Archived "${updated.location}".` : `Unarchived "${updated.location}".`, "success");
      card.remove();
      placeTripCard(updated);
      refreshCounts();
    },
  });

  actions.append(deleteBtn, archiveBtn, Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildTripEditPane(card, trip) {
  const pane = Global.el("div", { class: "edit-pane" });

  const locationInput = Global.el("input", { type: "text", value: trip.location, required: "required" });
  const startInput = Global.el("input", { type: "date", value: Global.toISODate(trip.start_date) });
  const endInput = Global.el("input", { type: "date", value: Global.toISODate(trip.end_date) });

  pane.appendChild(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Location" }), locationInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date" }), endInput]),
    ])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => {
      card.replaceWith(tripCardElement(trip, { expanded: true }));
    },
  });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const location = locationInput.value.trim();
      if (!location) {
        Global.showMessage("Location is required.", "error");
        return;
      }
      try {
        const updated = await Global.fetchJSON(`${TRIPS_API}/${trip.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location,
            start_date: Global.dateInputToISO(startInput.value),
            end_date: Global.dateInputToISO(endInput.value),
          }),
        });
        Global.showMessage(`Saved "${location}".`, "success");
        card.remove();
        placeTripCard(updated, { expanded: true });
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function placeTripCard(trip, opts = {}) {
  const list = trip.archived ? document.getElementById("archived-trips-list") : document.getElementById("trips-list");
  const card = tripCardElement(trip, opts);
  list.appendChild(card);
  applyIcons(card);
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
  const trips = await Global.fetchJSON(TRIPS_API);
  const tripsList = document.getElementById("trips-list");
  const archivedList = document.getElementById("archived-trips-list");
  tripsList.innerHTML = "";
  archivedList.innerHTML = "";
  for (const trip of trips) placeTripCard(trip);
  refreshCounts();
}

function initAddTripForm() {
  const container = document.getElementById("add-trip-container");
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Trip" });

  const locationInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Paris, France" });
  const startInput = Global.el("input", { type: "date" });
  const endInput = Global.el("input", { type: "date" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Location *" }), locationInput]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Start date" }), startInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "End date" }), endInput]),
    ]),
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
  const submitBtn = Global.el("button", { type: "submit", class: "save-btn", text: "Add trip" });
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
      const created = await Global.fetchJSON(TRIPS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location,
          start_date: Global.dateInputToISO(startInput.value),
          end_date: Global.dateInputToISO(endInput.value),
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${location}".`, "success");
      placeTripCard(created, { expanded: true });
      refreshCounts();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

initAddTripForm();
loadTrips().catch((err) => Global.showMessage(err.message, "error"));
