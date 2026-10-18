// Standalone places page - every reusable Place (see models.Place), each
// with its own overall rating/review, optional photos, and however many
// activities currently link to it (shown, not editable from here - an
// activity's own scheduling/visit-specific rating still lives on that
// activity, via activity-shared.js on activities.html/trip.html).

const PLACES_API = `${API_BASE}/places`;

// ?id=<place id> - the "🔗 View place →" link on a place-linked activity
// (activity-shared.js) lands here with that one place already expanded and
// scrolled to, same deep-link pattern as activities.html's own ?edit=.
const pageParams = new URLSearchParams(window.location.search);
let deepLinkPlaceId = pageParams.get("id") ? Number(pageParams.get("id")) : null;
if (pageParams.get("id")) {
  // Dropped from the URL so refreshing the page doesn't re-jump every time.
  const url = new URL(window.location.href);
  url.searchParams.delete("id");
  window.history.replaceState({}, "", url);
}

// Category assignment (a multiselect - buildCategoryMultiSelect, common.js
// - not the manager, which lives on activities.html, same split Activity's
// own form already uses) and its card-summary badges
// (soleCategoryFor/categoryBadgeElements, common.js - whole-card tint for
// exactly one category, small per-category badges for zero or several,
// same rule activity-shared.js's cards use) live in common.js now, shared
// rather than reimplemented here.

// --- photo gallery (plain binary storage, no processing at all - see
// models.PlaceImage) -------------------------------------------------------

function placePhotoGallery(place, onChanged) {
  const wrap = Global.el("div", { class: "place-photo-gallery" });
  const grid = Global.el("div", { class: "place-photo-grid" });
  wrap.appendChild(grid);

  async function load() {
    grid.innerHTML = "";
    const photos = await Global.fetchJSON(`${PLACES_API}/${place.id}/photos`);
    for (const photo of photos) {
      const item = Global.el("div", { class: "place-photo-item" }, [
        Global.el("img", { src: `${PLACES_API}/${place.id}/photos/${photo.id}`, alt: photo.filename }),
        Global.el("button", {
          type: "button",
          class: "place-photo-remove",
          "aria-label": `Remove ${photo.filename}`,
          text: "×",
          onclick: async () => {
            if (!confirm("Remove this photo?")) return;
            await Global.fetchJSON(`${PLACES_API}/${place.id}/photos/${photo.id}`, { method: "DELETE" });
            load();
          },
        }),
      ]);
      grid.appendChild(item);
    }
  }
  load();

  const fileInput = Global.el("input", { type: "file", accept: "image/*" });
  const uploadBtn = Global.el("button", {
    type: "button",
    class: "secondary-btn",
    text: "Add photo",
    onclick: async () => {
      const file = fileInput.files[0];
      if (!file) {
        Global.showMessage("Choose a photo first.", "error");
        return;
      }
      const body = new FormData();
      body.append("file", file);
      try {
        // A plain FormData body - Global.fetchJSON passes options straight
        // to fetch() without forcing a Content-Type, so the browser sets
        // the correct multipart boundary itself (same reasoning as
        // trip.js's dog-care attachment upload).
        await Global.fetchJSON(`${PLACES_API}/${place.id}/photos`, { method: "POST", body });
        fileInput.value = "";
        Global.showMessage("Photo added.", "success");
        load();
        if (onChanged) onChanged();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });
  wrap.appendChild(Global.el("div", { class: "place-photo-upload" }, [fileInput, uploadBtn]));
  return wrap;
}

// --- card (view/edit, same pattern as Stay/TravelSegment/DogCareBooking) --

function placeCardElement(place, { expanded = false } = {}) {
  // Same rule as an activity card (activity-shared.js) - whole-card tint
  // only for exactly one category, small per-category badges otherwise.
  const soleCategory = soleCategoryFor(place.category_ids);
  const card = Global.el("div", {
    class: "item-card" + (expanded ? " expanded" : "") + (soleCategory ? " has-category" : ""),
    "data-id": place.id,
  });
  if (soleCategory) {
    card.style.setProperty("--cat-color", soleCategory.color);
    card.style.setProperty("--cat-text-color", soleCategory.text_color === "light" ? "#ffffff" : "#000000");
  }

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  summary.appendChild(Global.el("span", { class: "item-summary-title", text: place.name }));
  const ratingLabel = starsDisplay(place.rating);
  if (ratingLabel) summary.appendChild(Global.el("span", { class: "item-badge-rating", text: ratingLabel }));
  if (soleCategory) {
    summary.appendChild(Global.el("span", { class: "item-summary-category-label", text: soleCategory.name }));
  } else {
    for (const badge of categoryBadgeElements(place.category_ids)) summary.appendChild(badge);
  }
  if (place.city) summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: place.city }));

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });
  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildPlaceViewEdit(card, place));
  return card;
}

function buildPlaceViewEdit(card, place) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const viewPane = buildPlaceViewPane(card, place);
  const editPane = buildPlaceEditPane(card, place);
  wrap.append(viewPane, editPane);
  wireViewEditToggle(viewPane, editPane);
  return wrap;
}

function buildPlaceViewPane(card, place) {
  const pane = Global.el("div", { class: "view-pane" });

  const fields = [
    viewField("Description", place.description),
    viewField("Address", place.address),
    viewField("Phone", place.phone_number),
    viewField("Review", place.review),
  ].filter(Boolean);
  if (fields.length) pane.appendChild(Global.el("div", { class: "view-fields" }, fields));

  const links = Global.el("div", { class: "view-links" });
  if (place.url) links.appendChild(Global.el("a", { href: place.url, target: "_blank", rel: "noopener noreferrer", class: "secondary-btn", text: "Visit website →" }));
  if (place.address) {
    links.appendChild(
      Global.el("a", {
        href: googleMapsSearchUrl(place.address),
        target: "_blank",
        rel: "noopener noreferrer",
        class: "secondary-btn",
        text: "Open map →",
        onclick: (e) => openGoogleMapsPreferringApp(e, "search", place.address),
      })
    );
  }
  if (links.children.length) pane.appendChild(links);

  if (place.url) pane.appendChild(buildPlaceScrapeSection(place));
  pane.appendChild(placePhotoGallery(place));

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${place.name}"? This cannot be undone.`)) return;
      try {
        await Global.fetchJSON(`${PLACES_API}/${place.id}`, { method: "DELETE" });
        Global.showMessage(`Deleted "${place.name}".`, "success");
        loadPlaces();
      } catch (err) {
        // 409 from the backend when an activity still links to this place
        // - fetchJSON surfaces the response body's `detail` as err.message.
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, Global.el("button", { type: "button", class: "secondary-btn edit-toggle-btn", text: "Edit" }));
  pane.appendChild(actions);
  return pane;
}

function buildPlaceScrapeSection(place) {
  const section = Global.el("div", { class: "scrape-section" });
  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: place.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        await Global.fetchJSON(`${PLACES_API}/${place.id}/scrape`, { method: "POST" });
        loadPlaces();
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  // renderScrapePreview lives in activity-shared.js, not loaded on this
  // page - it only reads the generic scrape_* fields, so a tiny local copy
  // is simpler than pulling in that whole (activity-specific) file just
  // for this one function.
  if (place.scrape_status === "success") {
    section.appendChild(
      Global.el("div", { class: "scrape-preview" }, [
        place.scraped_image_url ? Global.el("img", { src: place.scraped_image_url, alt: "" }) : null,
        Global.el("div", {}, [
          Global.el("div", { class: "scrape-preview-title", text: place.scraped_title || "" }),
          Global.el("div", { class: "scrape-preview-desc", text: place.scraped_description || "" }),
        ]),
      ].filter(Boolean))
    );
  } else if (place.scrape_status === "failed" || place.scrape_status === "unsupported") {
    section.appendChild(Global.el("p", { class: "note", text: place.scrape_error || "Couldn't fetch a preview for this URL." }));
  }
  return section;
}

function buildPlaceEditPane(card, place) {
  const pane = Global.el("div", { class: "edit-pane" });

  const nameInput = Global.el("input", { type: "text", value: place.name, required: "required" });
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = place.description || "";
  const urlInput = Global.el("input", { type: "url", value: place.url || "" });
  const addressInput = Global.el("input", { type: "text", value: place.address || "" });
  const cityInput = cityInputElement(place.city);
  const phoneInput = Global.el("input", { type: "text", value: place.phone_number || "" });
  const mapLinkInput = Global.el("input", { type: "url", value: place.map_link || "" });
  const categoryPicker = buildCategoryMultiSelect(place.category_ids);
  const ratingInput = ratingInputElement(place.rating);
  const reviewInput = Global.el("textarea", { rows: "3", placeholder: "What made this place worth remembering?" });
  reviewInput.value = place.review || "";

  pane.append(
    Global.el("div", { class: "item-fields" }, [
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
      Global.el("div", { class: "field-row" }, [
        Global.el("div", { class: "field" }, [Global.el("label", { text: "City" }), cityInput]),
        Global.el("div", { class: "field" }, [Global.el("label", { text: "Phone" }), phoneInput]),
      ]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Map link" }), mapLinkInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Categories" }), categoryPicker.element]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Rating" }), ratingInput]),
      Global.el("div", { class: "field" }, [Global.el("label", { text: "Review" }), reviewInput]),
    ])
  );

  const actions = Global.el("div", { class: "item-actions" });

  const cancelBtn = Global.el("button", {
    type: "button",
    class: "cancel-btn cancel-edit-btn",
    text: "Cancel",
    onclick: () => card.replaceWith(placeCardElement(place, { expanded: true })),
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
        await Global.fetchJSON(`${PLACES_API}/${place.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            address: addressInput.value.trim() || null,
            city: cityInput.value.trim() || null,
            phone_number: phoneInput.value.trim() || null,
            map_link: mapLinkInput.value.trim() || null,
            category_ids: categoryPicker.getSelectedIds(),
            rating: ratingInput.value,
            review: reviewInput.value.trim() || null,
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        loadCitiesCache();
        loadPlaces();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(cancelBtn, saveBtn);
  pane.appendChild(actions);
  return pane;
}

// --- list, filters, add form -----------------------------------------------

let loadedPlaces = [];
let cityFilter = new Set();
let categoryFilter = new Set();
let ratingFilter = new Set();

function renderPlaceList() {
  const list = document.getElementById("places-list");
  list.innerHTML = "";
  const filtered = loadedPlaces.filter(
    (p) =>
      (cityFilter.size === 0 || (p.city && cityFilter.has(p.city))) &&
      (categoryFilter.size === 0 || p.category_ids.some((id) => categoryFilter.has(String(id)))) &&
      (ratingFilter.size === 0 || (p.rating && ratingFilter.has(String(p.rating))))
  );
  let deepLinkCard = null;
  for (const place of filtered) {
    const isDeepLinkTarget = place.id === deepLinkPlaceId;
    const card = placeCardElement(place, { expanded: isDeepLinkTarget });
    list.appendChild(card);
    if (isDeepLinkTarget) deepLinkCard = card;
  }
  if (deepLinkCard) deepLinkCard.scrollIntoView({ block: "center" });
  // Cleared unconditionally, not just on a match - same reasoning as
  // activities.js's pendingEditActivityId: a lingering id here would
  // wrongly auto-expand+scroll again on some later, unrelated re-render
  // (e.g. after a filter changes) once it's already been used once.
  deepLinkPlaceId = null;

  document.getElementById("place-count").textContent = loadedPlaces.length ? `${loadedPlaces.length}` : "";
  document.getElementById("places-empty-state").hidden = loadedPlaces.length !== 0;
  const filtersActive = cityFilter.size > 0 || categoryFilter.size > 0 || ratingFilter.size > 0;
  document.getElementById("places-filtered-empty").hidden = !(loadedPlaces.length > 0 && filtered.length === 0 && filtersActive);
}

async function loadPlaces() {
  loadedPlaces = await Global.withLoading(document.getElementById("places-list"), Global.fetchJSON(PLACES_API));
  renderPlaceList();
}

function initCityFilter() {
  const mount = document.getElementById("place-city-filter-mount");
  mount.innerHTML = "";
  if (cities.length === 0) return;
  mount.appendChild(
    Global.buildMultiSelect({
      options: cities.map((c) => ({ value: c, label: c })),
      selected: [...cityFilter],
      placeholder: "All cities",
      onChange: (selected) => {
        cityFilter = new Set(selected);
        renderPlaceList();
      },
    })
  );
}

function initCategoryFilter() {
  const mount = document.getElementById("place-category-filter-mount");
  mount.innerHTML = "";
  if (categories.length === 0) return;
  mount.appendChild(
    Global.buildMultiSelect({
      options: categories.map((c) => ({ value: c.id, label: c.name, color: c.color })),
      selected: [],
      placeholder: "All categories",
      onChange: (selected) => {
        categoryFilter = new Set(selected.map(String));
        renderPlaceList();
      },
    })
  );
}

function initRatingFilter() {
  const mount = document.getElementById("place-rating-filter-mount");
  mount.innerHTML = "";
  mount.appendChild(
    Global.buildMultiSelect({
      options: [5, 4, 3, 2, 1].map((n) => ({ value: n, label: starsDisplay(n) })),
      selected: [],
      placeholder: "All ratings",
      onChange: (selected) => {
        ratingFilter = new Set(selected);
        renderPlaceList();
      },
    })
  );
}

function initAddPlaceForm() {
  const container = document.getElementById("add-place-container");
  const showBtn = Global.el("button", { type: "button", class: "add-toggle", text: "+ Add Place" });

  const nameInput = Global.el("input", { type: "text", required: "required", placeholder: "e.g. Cacao" });
  const descInput = Global.el("textarea", { rows: "2", placeholder: "Optional" });
  const urlInput = Global.el("input", { type: "url", placeholder: "https://..." });
  const addressInput = Global.el("input", { type: "text", placeholder: "Optional" });
  const cityInput = cityInputElement("");
  const categoryPicker = buildCategoryMultiSelect(null);
  const ratingInput = ratingInputElement(null);
  const reviewInput = Global.el("textarea", { rows: "3", placeholder: "Optional" });

  const form = Global.el("form", { class: "add-card hidden" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name *" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Address" }), addressInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "City" }), cityInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Categories" }), categoryPicker.element]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Rating" }), ratingInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Review" }), reviewInput]),
    Global.el("div", { class: "item-actions" }),
  ]);

  // form.reset() (both the Cancel button below and a successful submit)
  // only touches real form controls - neither ratingInputElement nor
  // buildCategoryMultiSelect (common.js) are native inputs, so each tracks
  // its own value/selection independently of whatever a native reset does
  // to the DOM. Hooking the form's own "reset" event once, rather than
  // repeating "reset it by hand" at both the Cancel and submit call sites,
  // covers both automatically. Reusing the multiselect's own "Clear"
  // button click - not reimplementing that logic here - keeps it in sync
  // with whatever buildMultiSelect's Clear actually does.
  form.addEventListener("reset", () => {
    ratingInput.value = null;
    categoryPicker.element.querySelector(".multiselect-clear")?.click();
  });

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
  const submitBtn = Global.el("button", { type: "submit", class: "save-btn", text: "Add place" });
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
      await Global.fetchJSON(PLACES_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: descInput.value.trim() || null,
          url: urlInput.value.trim() || null,
          address: addressInput.value.trim() || null,
          city: cityInput.value.trim() || null,
          category_ids: categoryPicker.getSelectedIds(),
          rating: ratingInput.value,
          review: reviewInput.value.trim() || null,
        }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadCitiesCache();
      loadPlaces();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  container.append(showBtn, form);
}

async function init() {
  await loadCategoriesCache();
  await loadCitiesCache();
  initAddPlaceForm();
  initCityFilter();
  initCategoryFilter();
  initRatingFilter();
  await loadPlaces();
}

init().catch((err) => Global.showMessage(err.message, "error"));
