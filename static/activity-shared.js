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
  const card = el("div", { class: "item-card" + (expanded ? " expanded" : "") + (activity.done ? " done" : ""), "data-id": activity.id });

  // A <div role="button"> rather than a real <button> - the done checkbox
  // below is interactive content, which isn't valid (and is flaky for
  // keyboard/screen-reader nav) nested inside a real <button>. Same fix as
  // the Trip card's Agenda link (see app.js).
  const summary = el("div", { class: "item-summary", role: "button", tabindex: "0", "aria-expanded": String(expanded) });

  const doneCheckbox = el("input", {
    type: "checkbox",
    class: "item-summary-done-toggle",
    "aria-label": `Mark "${activity.name}" as done`,
  });
  // Set as a property, not an attrs["checked"] value passed to el() - the
  // "checked" HTML attribute is presence-based (setAttribute("checked",
  // "false") would still render it checked), same reason trip.js sets
  // bookedInput.checked this way rather than through el()'s attrs.
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
      showMessage(err.message, "error");
    }
  });
  summary.appendChild(doneCheckbox);

  summary.appendChild(el("span", { class: "item-summary-title", text: activity.name }));

  // Small icon indicators, not full-text badges - a long date range or trip
  // name in the summary row was pushing the activity name itself down to a
  // sliver (or off entirely) once it needed to ellipsis. The icon alone is
  // enough to signal "this has a schedule / is on a trip"; the actual
  // values live in the expanded view pane's fields below, and as a title
  // tooltip here for a quick hover/long-press.
  const schedule = formatScheduleBadge(activity.scheduled_start, activity.scheduled_end);
  if (schedule) {
    summary.appendChild(
      el("span", { class: "item-summary-indicator", "data-icon": "calendar", "aria-hidden": "true", title: `Scheduled: ${schedule}` })
    );
  }

  const cost = formatCost(activity.cost);
  if (cost) summary.appendChild(el("span", { class: "item-badge item-badge-cost", text: cost }));

  if (showTripBadge) {
    const trip = activity.trips && activity.trips[0];
    if (trip) {
      summary.appendChild(
        el("span", { class: "item-summary-indicator", "data-icon": "compass", "aria-hidden": "true", title: `Trip: ${trip.location}` })
      );
    }
  }

  summary.appendChild(el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = el("div", { class: "item-details" + (expanded ? "" : " hidden") });
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
  const wrap = el("div", { class: "item-details-inner" });
  const viewPane = buildActivityViewPane(card, activity, opts);
  const editPane = buildActivityEditPane(card, activity, opts);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildActivityViewPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = el("div", { class: "view-pane" });

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
  if (fields.length) pane.appendChild(el("div", { class: "view-fields" }, fields));

  const links = el("div", { class: "view-links" });
  if (activity.url) links.appendChild(el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (activity.map_link) links.appendChild(el("a", { href: activity.map_link, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Open map →" }));
  if (activity.phone_number) links.appendChild(el("a", { href: `tel:${activity.phone_number}`, class: "secondary-btn", text: `Call ${activity.phone_number}` }));
  if (links.children.length) pane.appendChild(links);

  if (!fields.length && !links.children.length) {
    pane.appendChild(el("p", { class: "note", text: "No details yet - click Edit to add some." }));
  }

  // Yelp actively blocks server-side fetches (see the trip-clipper
  // extension for how Yelp data actually gets in) - showing a "Fetch
  // preview" button that would just always fail isn't useful.
  if (activity.url && !isYelpUrl(activity.url)) {
    pane.appendChild(buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }));
  }

  const actions = el("div", { class: "item-actions" });

  const deleteBtn = el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${activity.name}"? This cannot be undone.`)) return;
      await fetchJSON(`${ACTIVITIES_API}/${activity.id}`, { method: "DELETE" });
      card.remove();
      showMessage(`Deleted "${activity.name}".`, "success");
      if (onDeleted) onDeleted(activity);
    },
  });
  actions.append(deleteBtn);

  if (onUnlink) {
    actions.append(
      el("button", {
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
  actions.append(el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
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
  const wrap = el("div", { class: "duplicate-picker" });
  const triggerBtn = el("button", { type: "button", class: "secondary-btn", text: "Duplicate to trip..." });
  const pickerRow = el("div", { class: "duplicate-picker-row hidden" });
  const select = el("select", {});

  const confirmBtn = el("button", {
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
        showMessage(`Duplicated "${activity.name}" to ${tripLabel}.`, "success");
        pickerRow.classList.add("hidden");
        triggerBtn.classList.remove("hidden");
      } catch (err) {
        showMessage(err.message, "error");
      } finally {
        confirmBtn.disabled = false;
      }
    },
  });

  const cancelBtn = el("button", {
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
    select.appendChild(el("option", { value: "", text: "Loading trips..." }));
    try {
      const trips = await fetchJSON(TRIPS_API);
      const currentTripIds = new Set((activity.trips || []).map((t) => t.id));
      const options = trips.filter((t) => !currentTripIds.has(t.id));
      select.innerHTML = "";
      if (options.length === 0) {
        select.appendChild(el("option", { value: "", text: "No other trips yet" }));
      } else {
        select.disabled = false;
        confirmBtn.disabled = false;
        select.appendChild(el("option", { value: "", text: "Choose a trip..." }));
        for (const trip of options) {
          select.appendChild(
            el("option", { value: String(trip.id), text: trip.archived ? `${trip.location} (archived)` : trip.location })
          );
        }
      }
    } catch (err) {
      select.innerHTML = "";
      select.appendChild(el("option", { value: "", text: "Failed to load trips" }));
      showMessage(err.message, "error");
    }
  });

  wrap.append(triggerBtn, pickerRow);
  return wrap;
}

function buildActivityEditPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = el("div", { class: "edit-pane" });

  const nameInput = el("input", { type: "text", value: activity.name, required: "required" });
  const descInput = el("textarea", { rows: "2" });
  descInput.value = activity.description || "";
  const notesInput = el("textarea", { rows: "2" });
  notesInput.value = activity.notes || "";
  const urlInput = el("input", { type: "url", value: activity.url || "" });
  const costInput = el("input", { type: "number", min: "0", step: "1", value: activity.cost ?? "" });
  const confirmationInput = el("input", { type: "text", value: activity.confirmation_number || "" });
  const addressInput = el("input", { type: "text", value: activity.address || "" });
  const phoneInput = el("input", { type: "tel", value: activity.phone_number || "" });
  const mapLinkInput = el("input", { type: "url", value: activity.map_link || "" });
  const scheduledStartInput = el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_start) });
  const scheduledEndInput = el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_end) });

  const fields = el("div", { class: "item-fields" }, [
    el("div", { class: "field" }, [el("label", { text: "Name" }), nameInput]),
    el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]),
    el("div", { class: "field" }, [el("label", { text: "Notes" }), notesInput]),
    el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]),
    el("div", { class: "field" }, [el("label", { text: "Address" }), addressInput]),
    el("div", { class: "field" }, [el("label", { text: "Phone" }), phoneInput]),
    el("div", { class: "field" }, [el("label", { text: "Map link" }), mapLinkInput]),
    el("div", { class: "field" }, [el("label", { text: "Cost ($)" }), costInput]),
    el("div", { class: "field" }, [el("label", { text: "Confirmation #" }), confirmationInput]),
    // Usually set by dragging onto a trip's agenda page rather than typed
    // here, but editable directly too (e.g. to nudge a time or clear it).
    el("div", { class: "field" }, [el("label", { text: "Scheduled start" }), scheduledStartInput]),
    el("div", { class: "field" }, [el("label", { text: "Scheduled end" }), scheduledEndInput]),
  ]);
  pane.appendChild(fields);

  const actions = el("div", { class: "item-actions" });

  const cancelBtn = el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => {
      card.replaceWith(activityCardElement(activity, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
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
      const costValue = costInput.value.trim();
      if ((scheduledStartInput.value && !scheduledEndInput.value) || (!scheduledStartInput.value && scheduledEndInput.value)) {
        showMessage("Set both a scheduled start and end, or clear both.", "error");
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
        showMessage(`Saved "${name}".`, "success");
        if (onChanged) onChanged(updated);
        card.replaceWith(activityCardElement(updated, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
      } catch (err) {
        showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

function buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const section = el("div", { class: "scrape-section" });
  const scrapeBtn = el("button", {
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
        showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapePreview(activity));
  return section;
}

function renderScrapePreview(record) {
  if (record.scrape_status === "success") {
    const preview = el("div", { class: "scrape-preview" });
    if (record.scraped_image_url) {
      preview.appendChild(el("img", { src: record.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = el("div", { class: "scrape-text" });
    if (record.scraped_title) textWrap.appendChild(el("div", { class: "scrape-title", text: record.scraped_title }));
    if (record.scraped_description) textWrap.appendChild(el("div", { class: "scrape-description", text: record.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (record.scrape_status === "failed") {
    return el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${record.scrape_error || "unknown error"}` });
  }
  if (record.scrape_status === "unsupported") {
    return el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return el("div", { class: "scrape-note", text: "" });
}

// The create form itself - identical on both pages. tripId, when given,
// auto-associates the new activity to that trip on save (the only
// behavioral difference between the two call sites). `prefill` (from the
// trip-clipper extension's ?prefill= param, see activities.js) fills in
// initial values for review before saving - nothing is ever auto-submitted.
function newActivityFormElement({ tripId = null, onCreated, prefill = null } = {}) {
  const form = el("form", { class: "add-card hidden" });
  const nameInput = el("input", { type: "text", required: "required", placeholder: "e.g. Louvre Museum", value: prefill?.name || "" });
  const descInput = el("textarea", { rows: "2", placeholder: "Optional notes" });
  descInput.value = prefill?.description || "";
  const notesInput = el("textarea", { rows: "2", placeholder: "Optional" });
  const urlInput = el("input", { type: "url", placeholder: "https://...", value: prefill?.url || "" });
  const addressInput = el("input", { type: "text", placeholder: "Optional", value: prefill?.address || "" });
  const phoneInput = el("input", { type: "tel", placeholder: "Optional", value: prefill?.phone_number || "" });
  const mapLinkInput = el("input", { type: "url", placeholder: "Optional", value: prefill?.map_link || "" });
  const costInput = el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const confirmationInput = el("input", { type: "text", placeholder: "Optional" });

  form.append(
    el("div", { class: "field" }, [el("label", { text: "Name *" }), nameInput]),
    el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]),
    el("div", { class: "field" }, [el("label", { text: "Notes" }), notesInput]),
    el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]),
    el("div", { class: "field" }, [el("label", { text: "Address" }), addressInput]),
    el("div", { class: "field-row" }, [
      el("div", { class: "field" }, [el("label", { text: "Phone" }), phoneInput]),
      el("div", { class: "field" }, [el("label", { text: "Map link" }), mapLinkInput]),
    ]),
    el("div", { class: "field-row" }, [
      el("div", { class: "field" }, [el("label", { text: "Cost ($)" }), costInput]),
      el("div", { class: "field" }, [el("label", { text: "Confirmation #" }), confirmationInput]),
    ]),
    el("div", { class: "item-actions" }, [
      el("button", { type: "submit", class: "save-btn", text: "Add activity" }),
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
      showMessage(`Added "${name}".`, "success");
      if (onCreated) onCreated(created);
    } catch (err) {
      showMessage(err.message, "error");
    }
  });

  return form;
}

// Wires up the "+ Add Activity" toggle button + form together, the same
// show/cancel behavior used across every add-card in this app. Pass
// `prefill` + `autoOpen: true` to land with the form already open and
// filled in (the trip-clipper extension flow).
function initAddActivityToggle(container, { tripId = null, onCreated, prefill = null, autoOpen = false } = {}) {
  const showBtn = el("button", { type: "button", class: "add-toggle", text: "+ Add Activity" });
  const form = newActivityFormElement({
    tripId,
    prefill,
    onCreated: (created) => {
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      if (onCreated) onCreated(created);
    },
  });
  const cancelBtn = el("button", { type: "button", class: "cancel-btn", text: "Cancel" });
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
