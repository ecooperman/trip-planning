// Shared between activities.html (standalone activities) and trip.html
// (activities within a trip) - this is the ONE place the activity form and
// card live, so both pages render/behave identically. The only thing that
// differs between the two call sites is whether a tripId is passed in: if
// it is, a newly-created activity is associated to that trip on save.
//
// Each card is collapsed-by-default; expanding it shows a read-only view
// pane (with an Edit button) rather than the form directly - clicking Edit
// swaps to the form (edit pane), Cancel swaps back without saving. See
// wireViewEditToggle in common.js for the swap mechanism itself.

const ACTIVITIES_API = `${API_BASE}/activities`;

function activityCardElement(activity, opts = {}) {
  const { expanded = false, showTripBadge = false, onChanged, onDeleted, onUnlink } = opts;
  const card = Theme.el("div", { class: "item-card" + (expanded ? " expanded" : "") + (activity.done ? " done" : ""), "data-id": activity.id });

  // A <div role="button"> rather than a real <button> - the done checkbox
  // below is interactive content, which isn't valid (and is flaky for
  // keyboard/screen-reader nav) nested inside a real <button>. Same fix as
  // the Trip card's Agenda link (see app.js).
  const summary = Theme.el("div", { class: "item-summary", role: "button", tabindex: "0", "aria-expanded": String(expanded) });

  const doneCheckbox = Theme.el("input", {
    type: "checkbox",
    class: "item-summary-done-toggle",
    "aria-label": `Mark "${activity.name}" as done`,
  });
  // Set as a property, not an attrs["checked"] value passed to Theme.el() - the
  // "checked" HTML attribute is presence-based (setAttribute("checked",
  // "false") would still render it checked), same reason trip.js sets
  // bookedInput.checked this way rather than through Theme.el()'s attrs.
  doneCheckbox.checked = activity.done;
  doneCheckbox.addEventListener("click", (e) => e.stopPropagation());
  doneCheckbox.addEventListener("change", async () => {
    const done = doneCheckbox.checked;
    try {
      const updated = await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ done }),
      });
      activity.done = updated.done;
      card.classList.toggle("done", updated.done);
      if (onChanged) onChanged(updated);
    } catch (err) {
      doneCheckbox.checked = !done;
      Theme.showMessage(err.message, "error");
    }
  });
  summary.appendChild(doneCheckbox);

  summary.appendChild(Theme.el("span", { class: "item-summary-title", text: activity.name }));

  // Small icon indicators, not full-text badges - a long date range or trip
  // name in the summary row was pushing the activity name itself down to a
  // sliver (or off entirely) once it needed to ellipsis. The icon alone is
  // enough to signal "this has a schedule / is on a trip"; the actual
  // values live in the expanded view pane's fields below, and as a title
  // tooltip here for a quick hover/long-press.
  const schedule = formatScheduleBadge(activity.scheduled_start, activity.scheduled_end);
  if (schedule) {
    summary.appendChild(
      Theme.el("span", { class: "item-summary-indicator", "data-icon": "calendar", "aria-hidden": "true", title: `Scheduled: ${schedule}` })
    );
  }

  const cost = formatCost(activity.cost);
  if (cost) summary.appendChild(Theme.el("span", { class: "item-badge item-badge-cost", text: cost }));

  if (showTripBadge) {
    const trip = activity.trips && activity.trips[0];
    if (trip) {
      summary.appendChild(
        Theme.el("span", { class: "item-summary-indicator", "data-icon": "compass", "aria-hidden": "true", title: `Trip: ${trip.location}` })
      );
    }
  }

  summary.appendChild(Theme.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Theme.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
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
  details.appendChild(buildActivityViewEdit(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }));
  applyIcons(card);
  return card;
}

function buildActivityViewEdit(card, activity, opts) {
  const wrap = Theme.el("div", { class: "item-details-inner" });
  const viewPane = buildActivityViewPane(card, activity, opts);
  const editPane = buildActivityEditPane(card, activity, opts);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildActivityViewPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = Theme.el("div", { class: "view-pane" });

  // Scheduled/Trip used to be full-text badges in the summary row - now
  // just an icon there (see activityCardElement), so the actual values
  // need a home here instead of disappearing entirely.
  const tripField = showTripBadge
    ? viewField("Trip", activity.trips && activity.trips[0] ? activity.trips[0].location : "Unassociated")
    : null;

  const fields = [
    viewField("Scheduled", formatScheduleBadge(activity.scheduled_start, activity.scheduled_end)),
    tripField,
    viewField("Description", activity.description),
    viewField("Notes", activity.notes),
    viewField("Address", activity.address),
    viewField("Confirmation #", activity.confirmation_number),
  ].filter(Boolean);
  if (fields.length) pane.appendChild(Theme.el("div", { class: "view-fields" }, fields));

  const links = Theme.el("div", { class: "view-links" });
  if (activity.url) links.appendChild(Theme.el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (activity.map_link) links.appendChild(Theme.el("a", { href: activity.map_link, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Open map →" }));
  if (activity.phone_number) links.appendChild(Theme.el("a", { href: `tel:${activity.phone_number}`, class: "secondary-btn", text: `Call ${activity.phone_number}` }));
  if (links.children.length) pane.appendChild(links);

  if (!fields.length && !links.children.length) {
    pane.appendChild(Theme.el("p", { class: "note", text: "No details yet - click Edit to add some." }));
  }

  // Yelp actively blocks server-side fetches (see the trip-clipper
  // extension for how Yelp data actually gets in) - showing a "Fetch
  // preview" button that would just always fail isn't useful.
  if (activity.url && !isYelpUrl(activity.url)) {
    pane.appendChild(buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }));
  }

  const actions = Theme.el("div", { class: "item-actions" });

  const deleteBtn = Theme.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${activity.name}"? This cannot be undone.`)) return;
      await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, { method: "DELETE" });
      card.remove();
      Theme.showMessage(`Deleted "${activity.name}".`, "success");
      if (onDeleted) onDeleted(activity);
    },
  });
  actions.append(deleteBtn);

  if (onUnlink) {
    actions.append(
      Theme.el("button", {
        type: "button",
        class: "secondary-btn",
        text: "Remove from trip",
        onclick: async () => {
          if (!confirm(`Remove "${activity.name}" from this trip? It won't be deleted.`)) return;
          await onUnlink(activity);
        },
      })
    );
  }

  actions.append(buildDuplicatePicker(activity));
  actions.append(Theme.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);

  return pane;
}

// "Duplicate to trip..." - for re-doing an activity you already marked done
// on a past trip. Copies the place's own details (name/description/notes/
// address/phone/url/cost) to a brand-new activity on the chosen trip;
// deliberately drops confirmation_number, done, and scheduled_start/end -
// those describe a specific past booking/occurrence, not the place itself.
// Trips are fetched lazily (only once the trigger is clicked) rather than
// upfront on every card render, since most cards never open this.
function buildDuplicatePicker(activity) {
  const wrap = Theme.el("div", { class: "duplicate-picker" });
  const triggerBtn = Theme.el("button", { type: "button", class: "secondary-btn", text: "Duplicate to trip..." });
  const pickerRow = Theme.el("div", { class: "duplicate-picker-row hidden" });
  const select = Theme.el("select", {});

  const confirmBtn = Theme.el("button", {
    type: "button",
    class: "save-btn",
    text: "Duplicate",
    onclick: async () => {
      const tripId = select.value;
      if (!tripId) return;
      const tripLabel = select.options[select.selectedIndex].text;
      confirmBtn.disabled = true;
      try {
        await fetchJSON(ACTIVITIES_API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: activity.name,
            description: activity.description,
            url: activity.url,
            cost: activity.cost,
            address: activity.address,
            phone_number: activity.phone_number,
            map_link: activity.map_link,
            notes: activity.notes,
            trip_id: Number(tripId),
          }),
        });
        Theme.showMessage(`Duplicated "${activity.name}" to ${tripLabel}.`, "success");
        pickerRow.classList.add("hidden");
        triggerBtn.classList.remove("hidden");
      } catch (err) {
        Theme.showMessage(err.message, "error");
      } finally {
        confirmBtn.disabled = false;
      }
    },
  });

  const cancelBtn = Theme.el("button", {
    type: "button",
    class: "cancel-btn",
    text: "Cancel",
    onclick: () => {
      pickerRow.classList.add("hidden");
      triggerBtn.classList.remove("hidden");
    },
  });

  pickerRow.append(select, confirmBtn, cancelBtn);

  triggerBtn.addEventListener("click", async () => {
    triggerBtn.classList.add("hidden");
    pickerRow.classList.remove("hidden");
    select.innerHTML = "";
    select.disabled = true;
    confirmBtn.disabled = true;
    select.appendChild(Theme.el("option", { value: "", text: "Loading trips..." }));
    try {
      const trips = await fetchJSON(TRIPS_API);
      const currentTripIds = new Set((activity.trips || []).map((t) => t.id));
      const options = trips.filter((t) => !currentTripIds.has(t.id));
      select.innerHTML = "";
      if (options.length === 0) {
        select.appendChild(Theme.el("option", { value: "", text: "No other trips yet" }));
      } else {
        select.disabled = false;
        confirmBtn.disabled = false;
        select.appendChild(Theme.el("option", { value: "", text: "Choose a trip..." }));
        for (const trip of options) {
          select.appendChild(
            Theme.el("option", { value: String(trip.id), text: trip.archived ? `${trip.location} (archived)` : trip.location })
          );
        }
      }
    } catch (err) {
      select.innerHTML = "";
      select.appendChild(Theme.el("option", { value: "", text: "Failed to load trips" }));
      Theme.showMessage(err.message, "error");
    }
  });

  wrap.append(triggerBtn, pickerRow);
  return wrap;
}

function buildActivityEditPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = Theme.el("div", { class: "edit-pane" });

  const nameInput = Theme.el("input", { type: "text", value: activity.name, required: "required" });
  const descInput = Theme.el("textarea", { rows: "2" });
  descInput.value = activity.description || "";
  const notesInput = Theme.el("textarea", { rows: "2" });
  notesInput.value = activity.notes || "";
  const urlInput = Theme.el("input", { type: "url", value: activity.url || "" });
  const costInput = Theme.el("input", { type: "number", min: "0", step: "1", value: activity.cost ?? "" });
  const confirmationInput = Theme.el("input", { type: "text", value: activity.confirmation_number || "" });
  const addressInput = Theme.el("input", { type: "text", value: activity.address || "" });
  const phoneInput = Theme.el("input", { type: "tel", value: activity.phone_number || "" });
  const mapLinkInput = Theme.el("input", { type: "url", value: activity.map_link || "" });
  const scheduledStartInput = Theme.el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_start) });
  const scheduledEndInput = Theme.el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_end) });

  const fields = Theme.el("div", { class: "item-fields" }, [
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Name" }), nameInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Description" }), descInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Notes" }), notesInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "URL" }), urlInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Address" }), addressInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Phone" }), phoneInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Map link" }), mapLinkInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Cost ($)" }), costInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Confirmation #" }), confirmationInput]),
    // Usually set by dragging onto a trip's agenda page rather than typed
    // here, but editable directly too (e.g. to nudge a time or clear it).
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Scheduled start" }), scheduledStartInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Scheduled end" }), scheduledEndInput]),
  ]);
  pane.appendChild(fields);

  const actions = Theme.el("div", { class: "item-actions" });

  const cancelBtn = Theme.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => {
      card.replaceWith(activityCardElement(activity, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
    },
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
      const costValue = costInput.value.trim();
      if ((scheduledStartInput.value && !scheduledEndInput.value) || (!scheduledStartInput.value && scheduledEndInput.value)) {
        Theme.showMessage("Set both a scheduled start and end, or clear both.", "error");
        return;
      }
      try {
        const updated = await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            notes: notesInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            address: addressInput.value.trim() || null,
            phone_number: phoneInput.value.trim() || null,
            map_link: mapLinkInput.value.trim() || null,
            cost: costValue === "" ? null : Number(costValue),
            confirmation_number: confirmationInput.value.trim() || null,
            scheduled_start: datetimeLocalToISO(scheduledStartInput.value),
            scheduled_end: datetimeLocalToISO(scheduledEndInput.value),
          }),
        });
        Theme.showMessage(`Saved "${name}".`, "success");
        if (onChanged) onChanged(updated);
        card.replaceWith(activityCardElement(updated, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
      } catch (err) {
        Theme.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const section = Theme.el("div", { class: "scrape-section" });
  const scrapeBtn = Theme.el("button", {
    type: "button",
    class: "scrape-btn",
    text: activity.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await fetchJSON(`${ACTIVITIES_API}/${activity.id}/scrape`, { method: "POST" });
        if (onChanged) onChanged(updated);
        card.replaceWith(activityCardElement(updated, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Theme.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapePreview(activity));
  return section;
}

function renderScrapePreview(record) {
  if (record.scrape_status === "success") {
    const preview = Theme.el("div", { class: "scrape-preview" });
    if (record.scraped_image_url) {
      preview.appendChild(Theme.el("img", { src: record.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Theme.el("div", { class: "scrape-text" });
    if (record.scraped_title) textWrap.appendChild(Theme.el("div", { class: "scrape-title", text: record.scraped_title }));
    if (record.scraped_description) textWrap.appendChild(Theme.el("div", { class: "scrape-description", text: record.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (record.scrape_status === "failed") {
    return Theme.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${record.scrape_error || "unknown error"}` });
  }
  if (record.scrape_status === "unsupported") {
    return Theme.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Theme.el("div", { class: "scrape-note", text: "" });
}

// The create form itself - identical on both pages. tripId, when given,
// auto-associates the new activity to that trip on save (the only
// behavioral difference between the two call sites). `prefill` (from the
// trip-clipper extension's ?prefill= param, see activities.js) fills in
// initial values for review before saving - nothing is ever auto-submitted.
function newActivityFormElement({ tripId = null, onCreated, prefill = null } = {}) {
  const form = Theme.el("form", { class: "add-card hidden" });
  const nameInput = Theme.el("input", { type: "text", required: "required", placeholder: "e.g. Louvre Museum", value: prefill?.name || "" });
  const descInput = Theme.el("textarea", { rows: "2", placeholder: "Optional notes" });
  descInput.value = prefill?.description || "";
  const notesInput = Theme.el("textarea", { rows: "2", placeholder: "Optional" });
  const urlInput = Theme.el("input", { type: "url", placeholder: "https://...", value: prefill?.url || "" });
  const addressInput = Theme.el("input", { type: "text", placeholder: "Optional", value: prefill?.address || "" });
  const phoneInput = Theme.el("input", { type: "tel", placeholder: "Optional", value: prefill?.phone_number || "" });
  const mapLinkInput = Theme.el("input", { type: "url", placeholder: "Optional", value: prefill?.map_link || "" });
  const costInput = Theme.el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const confirmationInput = Theme.el("input", { type: "text", placeholder: "Optional" });

  form.append(
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Name *" }), nameInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Description" }), descInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Notes" }), notesInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "URL" }), urlInput]),
    Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Address" }), addressInput]),
    Theme.el("div", { class: "field-row" }, [
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Phone" }), phoneInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Map link" }), mapLinkInput]),
    ]),
    Theme.el("div", { class: "field-row" }, [
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Cost ($)" }), costInput]),
      Theme.el("div", { class: "field" }, [Theme.el("label", { text: "Confirmation #" }), confirmationInput]),
    ]),
    Theme.el("div", { class: "item-actions" }, [
      Theme.el("button", { type: "submit", class: "save-btn", text: "Add activity" }),
    ])
  );

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    const costValue = costInput.value.trim();
    try {
      const created = await fetchJSON(ACTIVITIES_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: descInput.value.trim() || null,
          notes: notesInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          address: addressInput.value.trim() || null,
          phone_number: phoneInput.value.trim() || null,
          map_link: mapLinkInput.value.trim() || null,
          cost: costValue === "" ? null : Number(costValue),
          confirmation_number: confirmationInput.value.trim() || null,
          trip_id: tripId,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      Theme.showMessage(`Added "${name}".`, "success");
      if (onCreated) onCreated(created);
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });

  return form;
}

// Wires up the "+ Add Activity" toggle button + form together, the same
// show/cancel behavior used across every add-card in this app. Pass
// `prefill` + `autoOpen: true` to land with the form already open and
// filled in (the trip-clipper extension flow).
function initAddActivityToggle(container, { tripId = null, onCreated, prefill = null, autoOpen = false } = {}) {
  const showBtn = Theme.el("button", { type: "button", class: "add-toggle", text: "+ Add Activity" });
  const form = newActivityFormElement({
    tripId,
    prefill,
    onCreated: (created) => {
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      if (onCreated) onCreated(created);
    },
  });
  const cancelBtn = Theme.el("button", { type: "button", class: "cancel-btn", text: "Cancel" });
  cancelBtn.addEventListener("click", () => {
    form.reset();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  });
  form.querySelector(".item-actions").appendChild(cancelBtn);

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    form.querySelector("input").focus();
  });

  container.append(showBtn, form);

  if (autoOpen) {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
  }
}
