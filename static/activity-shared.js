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
const CATEGORIES_API = `${API_BASE}/categories`;
// CITIES_API/cities/loadCitiesCache/cityInputElement moved to common.js -
// index.html (the homepage's own trip list/edit) needs the same city
// datalist too, and common.js is the one file already shared by every
// page (this one isn't loaded there).

// Same pattern as time-management's Category: a user-managed name+color
// label, optionally assigned to an activity (category_id, nullable - see
// models.py for why this one's optional unlike Task's). Fetched once into
// module state rather than nested on every activity from the API, so both
// pages' loadActivities() should `await loadCategoriesCache()` before
// building any cards/forms - see activities.js/trip.js.
let categories = [];
let categoriesById = {};

async function loadCategoriesCache() {
  categories = await Global.fetchJSON(CATEGORIES_API);
  categoriesById = {};
  for (const category of categories) categoriesById[category.id] = category;
  return categories;
}

function buildCategorySelect(selectedId) {
  const select = Global.el("select", {});
  select.appendChild(Global.el("option", { value: "", text: "No category" }));
  for (const category of categories) {
    select.appendChild(Global.el("option", { value: String(category.id), text: category.name }));
  }
  select.value = selectedId ? String(selectedId) : "";
  return select;
}


// Shared by activities.html and trip.html (see their loadActivities) - the
// same three-way split, so archived and done mean the same thing and look
// the same wherever activities show up. archived wins over done for
// grouping purposes (an activity can't usefully be in both lists at once) -
// it's the "tucked away, not part of the active plan" bucket, whether or
// not it ever got marked done first.
function partitionActivities(activities) {
  const active = [];
  const done = [];
  const archived = [];
  for (const activity of activities) {
    if (activity.archived) archived.push(activity);
    else if (activity.done) done.push(activity);
    else active.push(activity);
  }
  return { active, done, archived };
}

function activityCardElement(activity, opts = {}) {
  const { expanded = false, showTripBadge = false, onChanged, onDeleted, onUnlink, startInEdit = false } = opts;
  const category = activity.category_id ? categoriesById[activity.category_id] : null;
  const card = Global.el("div", {
    class:
      "item-card" +
      (expanded ? " expanded" : "") +
      (activity.done ? " done" : "") +
      (activity.archived ? " archived" : "") +
      (category ? " has-category" : ""),
    "data-id": activity.id,
  });
  // The category, if any, tints the whole summary row background (see
  // .item-card.has-category in style.css) - text color is a per-category
  // dark/light choice (category.text_color) rather than computed, since
  // legible contrast against an arbitrary picked color is subjective.
  if (category) {
    card.style.setProperty("--cat-color", category.color);
    card.style.setProperty("--cat-text-color", category.text_color === "light" ? "#ffffff" : "#000000");
  }

  // A <div role="button"> rather than a real <button> - the done checkbox
  // below is interactive content, which isn't valid (and is flaky for
  // keyboard/screen-reader nav) nested inside a real <button>. Same fix as
  // the Trip card's Agenda link (see app.js).
  const summary = Global.el("div", { class: "item-summary", role: "button", tabindex: "0", "aria-expanded": String(expanded) });

  const doneCheckbox = Global.el("input", {
    type: "checkbox",
    class: "item-summary-done-toggle",
    "aria-label": `Mark "${activity.name}" as done`,
  });
  // Set as a property, not an attrs["checked"] value passed to Global.el() - the
  // "checked" HTML attribute is presence-based (setAttribute("checked",
  // "false") would still render it checked), same reason trip.js sets
  // bookedInput.checked this way rather than through Global.el()'s attrs.
  doneCheckbox.checked = activity.done;
  doneCheckbox.addEventListener("click", (e) => e.stopPropagation());
  doneCheckbox.addEventListener("change", async () => {
    const done = doneCheckbox.checked;
    try {
      const updated = await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ done }),
      });
      activity.done = updated.done;
      card.classList.toggle("done", updated.done);
      if (onChanged) onChanged(updated);
    } catch (err) {
      doneCheckbox.checked = !done;
      Global.showMessage(err.message, "error");
    }
  });
  summary.appendChild(doneCheckbox);

  summary.appendChild(Global.el("span", { class: "item-summary-title", text: activity.name }));

  // Small icon indicators, not full-text badges - a long date range or trip
  // name in the summary row was pushing the activity name itself down to a
  // sliver (or off entirely) once it needed to ellipsis. When the activity
  // has an associated trip, each one doubles as a shortcut straight to
  // that trip's agenda/page - padding + negative margin gives a generous
  // tap target without extra visual space (same trick as the Agenda link
  // on trip cards, see app.js), and stopPropagation keeps it from also
  // toggling the card open. No trip to link to (or, for the compass, not
  // showing a trip badge at all on this page) just falls back to a plain
  // non-clickable indicator, tooltip only.
  const trip = activity.trips && activity.trips[0];

  const schedule = formatScheduleBadge(activity.scheduled_start, activity.scheduled_end);
  if (schedule) {
    const scheduleTitle = `Scheduled: ${schedule}`;
    if (trip) {
      const link = Global.el(
        "a",
        {
          href: `agenda.html?id=${trip.id}`,
          class: "item-summary-icon-link activity-summary-schedule-link",
          "aria-label": scheduleTitle,
          title: scheduleTitle,
        },
        [Global.el("span", { class: "btn-icon", "data-icon": "calendar", "aria-hidden": "true" })]
      );
      link.addEventListener("click", (e) => e.stopPropagation());
      summary.appendChild(link);
    } else {
      summary.appendChild(
        Global.el("span", { class: "item-summary-indicator", "data-icon": "calendar", "aria-hidden": "true", title: scheduleTitle })
      );
    }
  }

  const cost = formatCost(activity.cost);
  if (cost) summary.appendChild(Global.el("span", { class: "item-badge item-badge-cost", text: cost }));

  if (showTripBadge && trip) {
    const tripTitle = `Trip: ${trip.location}`;
    const link = Global.el(
      "a",
      {
        href: `trip.html?id=${trip.id}`,
        class: "item-summary-icon-link activity-summary-trip-link",
        "aria-label": tripTitle,
        title: tripTitle,
      },
      [Global.el("span", { class: "btn-icon", "data-icon": "compass", "aria-hidden": "true" })]
    );
    link.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(link);
  }

  // The whole row is already tinted with the category's color (see
  // .item-card.has-category in style.css), so naming it doesn't need its
  // own box/background on top of that - just the name in plain text, in
  // whichever text color (--cat-text-color, set above) reads legibly
  // against that background.
  if (category) {
    summary.appendChild(Global.el("span", { class: "item-summary-category-label", text: category.name }));
  }

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
  details.appendChild(buildActivityViewEdit(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge, startInEdit }));
  applyIcons(card);
  return card;
}

function buildActivityViewEdit(card, activity, opts) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildActivityViewPane(card, activity, opts);
  const editPane = buildActivityEditPane(card, activity, opts);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  // Lands straight in the edit form rather than the view pane - used by
  // the "Edit" link on agenda.html's entries (see activities.js's
  // ?edit=<id> handling), so you don't have to expand then click Edit
  // yourself after following the link.
  if (opts.startInEdit) {
    viewPane.classList.add("hidden");
    editPane.classList.remove("hidden");
  }
  return wrap;
}

function buildActivityViewPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = Global.el("div", { class: "view-pane" });

  // Scheduled/Trip used to be full-text badges in the summary row - now
  // just an icon there (see activityCardElement), so the actual values
  // need a home here instead of disappearing entirely.
  const tripField = showTripBadge
    ? viewField("Trip", activity.trips && activity.trips[0] ? activity.trips[0].location : "Unassociated")
    : null;
  const category = activity.category_id ? categoriesById[activity.category_id] : null;

  const fields = [
    viewField("Scheduled", formatScheduleBadge(activity.scheduled_start, activity.scheduled_end)),
    tripField,
    viewField("Category", category ? category.name : null),
    viewField("Description", activity.description),
    viewField("Notes", activity.notes),
    viewField("Address", activity.address),
    viewField("City", activity.city),
    viewField("Confirmation #", activity.confirmation_number),
  ].filter(Boolean);
  if (fields.length) pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  const links = Global.el("div", { class: "view-links" });
  if (activity.url) links.appendChild(Global.el("a", { href: activity.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (activity.map_link) links.appendChild(Global.el("a", { href: activity.map_link, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Open map →" }));
  if (activity.phone_number) links.appendChild(Global.el("a", { href: `tel:${activity.phone_number}`, class: "secondary-btn", text: `Call ${activity.phone_number}` }));
  if (links.children.length) pane.appendChild(links);

  if (!fields.length && !links.children.length) {
    pane.appendChild(Global.el("p", { class: "note", text: "No details yet - click Edit to add some." }));
  }

  // Yelp actively blocks server-side fetches (see the trip-clipper
  // extension for how Yelp data actually gets in) - showing a "Fetch
  // preview" button that would just always fail isn't useful.
  if (activity.url && !isYelpUrl(activity.url)) {
    pane.appendChild(buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }));
  }

  pane.appendChild(buildActivityDistancesSection(activity));

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${activity.name}"? This cannot be undone.`)) return;
      await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, { method: "DELETE" });
      card.remove();
      Global.showMessage(`Deleted "${activity.name}".`, "success");
      if (onDeleted) onDeleted(activity);
    },
  });
  actions.append(deleteBtn);

  if (onUnlink) {
    actions.append(
      Global.el("button", {
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

  // Independent of done - "didn't do this and won't" is archived, not
  // done; "did this" is done, not archived. Also settable in bulk by
  // archiving the whole trip (see crud.update_trip), which is why this
  // needs to exist at all rather than just being a manual-only toggle.
  actions.append(
    Global.el("button", {
      type: "button",
      class: "secondary-btn",
      text: activity.archived ? "Unarchive" : "Archive",
      onclick: async () => {
        const updated = await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ archived: !activity.archived }),
        });
        Global.showMessage(updated.archived ? `Archived "${updated.name}".` : `Unarchived "${updated.name}".`, "success");
        if (onChanged) onChanged(updated);
      },
    })
  );

  actions.append(buildDuplicatePicker(activity));
  actions.append(Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
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
  const wrap = Global.el("div", { class: "duplicate-picker" });
  const triggerBtn = Global.el("button", { type: "button", class: "secondary-btn", text: "Duplicate to trip..." });
  const pickerRow = Global.el("div", { class: "duplicate-picker-row hidden" });
  const select = Global.el("select", {});

  const confirmBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Duplicate",
    onclick: async () => {
      const tripId = select.value;
      if (!tripId) return;
      const tripLabel = select.options[select.selectedIndex].text;
      confirmBtn.disabled = true;
      try {
        await Global.fetchJSON(ACTIVITIES_API, {
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
        Global.showMessage(`Duplicated "${activity.name}" to ${tripLabel}.`, "success");
        pickerRow.classList.add("hidden");
        triggerBtn.classList.remove("hidden");
      } catch (err) {
        Global.showMessage(err.message, "error");
      } finally {
        confirmBtn.disabled = false;
      }
    },
  });

  const cancelBtn = Global.el("button", {
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
    select.appendChild(Global.el("option", { value: "", text: "Loading trips..." }));
    try {
      const trips = await Global.fetchJSON(TRIPS_API);
      const currentTripIds = new Set((activity.trips || []).map((t) => t.id));
      const options = trips.filter((t) => !currentTripIds.has(t.id));
      select.innerHTML = "";
      if (options.length === 0) {
        select.appendChild(Global.el("option", { value: "", text: "No other trips yet" }));
      } else {
        select.disabled = false;
        confirmBtn.disabled = false;
        select.appendChild(Global.el("option", { value: "", text: "Choose a trip..." }));
        for (const trip of options) {
          select.appendChild(
            Global.el("option", { value: String(trip.id), text: trip.archived ? `${trip.location} (archived)` : trip.location })
          );
        }
      }
    } catch (err) {
      select.innerHTML = "";
      select.appendChild(Global.el("option", { value: "", text: "Failed to load trips" }));
      Global.showMessage(err.message, "error");
    }
  });

  wrap.append(triggerBtn, pickerRow);
  return wrap;
}

function buildActivityEditPane(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const pane = Global.el("div", { class: "edit-pane" });

  const nameInput = Global.el("input", { type: "text", value: activity.name, required: "required" });
  const categorySelect = buildCategorySelect(activity.category_id);
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = activity.description || "";
  const notesInput = Global.el("textarea", { rows: "2" });
  notesInput.value = activity.notes || "";
  const urlInput = Global.el("input", { type: "url", value: activity.url || "" });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", value: activity.cost ?? "" });
  const confirmationInput = Global.el("input", { type: "text", value: activity.confirmation_number || "" });
  const addressInput = Global.el("input", { type: "text", value: activity.address || "" });
  const cityInput = cityInputElement(activity.city);
  const phoneInput = Global.el("input", { type: "tel", value: activity.phone_number || "" });
  const mapLinkInput = Global.el("input", { type: "url", value: activity.map_link || "" });
  const scheduledStartInput = Global.el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_start) });
  const scheduledEndInput = Global.el("input", { type: "datetime-local", value: toDatetimeLocal(activity.scheduled_end) });
  // Convenience: filling in just the start time auto-fills a plausible end
  // (start + 1h) so you don't have to type both. Only when end is still
  // blank, so it never clobbers an end that's already set - either typed
  // by hand, or already on the activity from a previous save.
  scheduledStartInput.addEventListener("change", () => {
    if (!scheduledStartInput.value || scheduledEndInput.value) return;
    scheduledEndInput.value = toDatetimeLocal(addMinutesISO(scheduledStartInput.value, 60));
  });

  const fields = Global.el("div", { class: "item-fields" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Category" }), categorySelect]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Notes" }), notesInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "City" }), cityInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Phone" }), phoneInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Map link" }), mapLinkInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Confirmation #" }), confirmationInput]),
    // Usually set by dragging onto a trip's agenda page rather than typed
    // here, but editable directly too (e.g. to nudge a time or clear it).
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Scheduled start" }), scheduledStartInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Scheduled end" }), scheduledEndInput]),
  ]);
  pane.appendChild(fields);

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => {
      card.replaceWith(activityCardElement(activity, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
    },
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
      const costValue = costInput.value.trim();
      if ((scheduledStartInput.value && !scheduledEndInput.value) || (!scheduledStartInput.value && scheduledEndInput.value)) {
        Global.showMessage("Set both a scheduled start and end, or clear both.", "error");
        return;
      }
      try {
        const updated = await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            category_id: categorySelect.value ? Number(categorySelect.value) : null,
            description: descInput.value.trim() || null,
            notes: notesInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            address: addressInput.value.trim() || null,
            city: cityInput.value.trim() || null,
            phone_number: phoneInput.value.trim() || null,
            map_link: mapLinkInput.value.trim() || null,
            cost: costValue === "" ? null : Number(costValue),
            confirmation_number: confirmationInput.value.trim() || null,
            scheduled_start: datetimeLocalToISO(scheduledStartInput.value),
            scheduled_end: datetimeLocalToISO(scheduledEndInput.value),
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        // Fire-and-forget - picks up a newly-typed city for the shared
        // datalist right away, without waiting on it before the card swap
        // below (a stale datalist for a few moments isn't worth blocking on).
        loadCitiesCache();
        if (onChanged) onChanged(updated);
        card.replaceWith(activityCardElement(updated, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

// "Distance to" - every real distance already calculated involving this
// activity (see Compare distances on activities.html), read straight from
// the cache (GET /api/activities/{id}/distances never calls Google
// itself) so a comparison you've already run stays visible on the
// activities it was about, without having to re-run it or remember which
// page you calculated it from. Nested <details>, lazy-loaded on first
// open (not fetched the moment this card renders) - a list of activities
// builds every card's view pane up front, and most cards' distance
// sections are never opened, so fetching for all of them eagerly would be
// pure waste.
function buildActivityDistancesSection(activity) {
  const details = Global.el("details", { class: "activity-distances-section" });
  const body = Global.el("div", { class: "activity-distances-body" });
  details.append(Global.el("summary", { text: "Distance to other activities" }), body);

  let loaded = false;
  details.addEventListener("toggle", async () => {
    if (!details.open || loaded) return;
    loaded = true;
    body.appendChild(Global.el("p", { class: "note", text: "Loading…" }));
    try {
      const entries = await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}/distances`);
      body.innerHTML = "";
      if (entries.length === 0) {
        body.appendChild(
          Global.el("p", { class: "note", text: 'Nothing calculated yet - use "Compare distances" on the Activities page.' })
        );
        return;
      }
      const list = Global.el("ul", { class: "distance-result-list" });
      for (const entry of entries) {
        const otherLabel = entry.other_activity_city ? `${entry.other_activity_name} — ${entry.other_activity_city}` : entry.other_activity_name;
        const arrow = entry.direction === "to" ? "→" : "←";
        const parts = [];
        if (entry.walking) parts.push(`Walk ${entry.walking.distance_text} · ${entry.walking.duration_text}`);
        if (entry.driving) parts.push(`Drive ${entry.driving.distance_text} · ${entry.driving.duration_text}`);
        list.appendChild(
          Global.el("li", {}, [
            Global.el("span", { class: "distance-result-names", text: `${arrow} ${otherLabel}` }),
            Global.el("span", { class: "distance-result-value", text: parts.join("  ·  ") }),
          ])
        );
      }
      body.appendChild(list);
    } catch (err) {
      body.innerHTML = "";
      body.appendChild(Global.el("p", { class: "note", text: `Couldn't load: ${err.message}` }));
      loaded = false; // let a retry (collapse + re-expand) try again rather than getting stuck empty
    }
  });

  return details;
}

function buildActivityScrapeSection(card, activity, { onChanged, onDeleted, onUnlink, showTripBadge }) {
  const section = Global.el("div", { class: "scrape-section" });
  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: activity.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await Global.fetchJSON(`${ACTIVITIES_API}/${activity.id}/scrape`, { method: "POST" });
        if (onChanged) onChanged(updated);
        card.replaceWith(activityCardElement(updated, { expanded: true, showTripBadge, onChanged, onDeleted, onUnlink }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapePreview(activity));
  return section;
}

function renderScrapePreview(record) {
  if (record.scrape_status === "success") {
    const preview = Global.el("div", { class: "scrape-preview" });
    if (record.scraped_image_url) {
      preview.appendChild(Global.el("img", { src: record.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Global.el("div", { class: "scrape-text" });
    if (record.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: record.scraped_title }));
    if (record.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: record.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (record.scrape_status === "failed") {
    return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${record.scrape_error || "unknown error"}` });
  }
  if (record.scrape_status === "unsupported") {
    return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Global.el("div", { class: "scrape-note", text: "" });
}

// The create form itself - identical on both pages. tripId, when given,
// auto-associates the new activity to that trip on save (the only
// behavioral difference between the two call sites). `prefill` (from the
// trip-clipper extension's ?prefill= param, see activities.js) fills in
// initial values for review before saving - nothing is ever auto-submitted.
function newActivityFormElement({ tripId = null, tripCity = null, onCreated, prefill = null } = {}) {
  const form = Global.el("form", { class: "add-card hidden" });
  const nameInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Louvre Museum", value: prefill?.name || "" });
  const categorySelect = buildCategorySelect(null);
  const descInput = Global.el("textarea", { rows: "2", placeholder: "Optional notes" });
  descInput.value = prefill?.description || "";
  const notesInput = Global.el("textarea", { rows: "2", placeholder: "Optional" });
  const urlInput = Global.el("input", { type: "url", placeholder: "https://...", value: prefill?.url || "" });
  const addressInput = Global.el("input", { type: "text", placeholder: "Optional", value: prefill?.address || "" });
  // Defaults to the trip's own city (most activities in a trip share one) -
  // still fully editable for a day trip elsewhere. Blank on activities.html
  // (no tripCity there - no trip context to default from).
  const cityInput = cityInputElement(tripCity);
  const phoneInput = Global.el("input", { type: "tel", placeholder: "Optional", value: prefill?.phone_number || "" });
  const mapLinkInput = Global.el("input", { type: "url", placeholder: "Optional", value: prefill?.map_link || "" });
  const costInput = Global.el("input", { type: "number", min: "0", step: "1", placeholder: "Optional" });
  const confirmationInput = Global.el("input", { type: "text", placeholder: "Optional" });

  form.append(
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name *" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Category" }), categorySelect]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Notes" }), notesInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "City" }), cityInput]),
    ]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Phone" }), phoneInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Map link" }), mapLinkInput]),
    ]),
    Global.el("div", { class: "field-row" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Cost ($)" }), costInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Confirmation #" }), confirmationInput]),
    ]),
    Global.el("div", { class: "item-actions" }, [
      Global.el("button", { type: "submit", class: "save-btn", text: "Add activity" }),
    ])
  );

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    const costValue = costInput.value.trim();
    try {
      const created = await Global.fetchJSON(ACTIVITIES_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          category_id: categorySelect.value ? Number(categorySelect.value) : null,
          description: descInput.value.trim() || null,
          notes: notesInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          address: addressInput.value.trim() || null,
          city: cityInput.value.trim() || null,
          phone_number: phoneInput.value.trim() || null,
          map_link: mapLinkInput.value.trim() || null,
          cost: costValue === "" ? null : Number(costValue),
          confirmation_number: confirmationInput.value.trim() || null,
          trip_id: tripId,
        }),
      });
      form.reset();
      cityInput.value = tripCity || ""; // form.reset() would otherwise blank the trip-city default back out
      form.classList.add("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadCitiesCache(); // fire-and-forget - same reasoning as the edit-pane save above
      if (onCreated) onCreated(created);
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  return form;
}

// Wires up the "+ Add Activity" toggle button + form together, the same
// show/cancel behavior used across every add-card in this app. Pass
// `prefill` + `autoOpen: true` to land with the form already open and
// filled in (the trip-clipper extension flow).
function initAddActivityToggle(container, { tripId = null, tripCity = null, onCreated, prefill = null, autoOpen = false } = {}) {
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Activity" });
  const form = newActivityFormElement({
    tripId,
    tripCity,
    prefill,
    onCreated: (created) => {
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      if (onCreated) onCreated(created);
    },
  });
  const cancelBtn = Global.el("button", { type: "button", class: "cancel-btn", text: "Cancel" });
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
