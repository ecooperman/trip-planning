// Standalone activities page - lists every activity (associated or not)
// and lets you create one without a trip. Uses the exact same form/card
// code (activity-shared.js) as the activities section on trip.html; the
// only difference is no tripId is passed, so nothing auto-associates.
//
// Also the landing page for the trip-clipper Chrome extension: it opens
// this page with a base64url-encoded ?prefill= param carrying whatever it
// read off the page you were looking at (see
// ../trip-clipper-chrome-extension), which just pre-fills and auto-opens
// the add-activity form below - nothing is ever saved without you clicking
// "Add activity" yourself.

// --- category management (same pattern as time-management's admin.js) ------
//
// The one place categories get created/renamed/recolored/deleted -
// assigning one to an activity happens on the activity's own form instead
// (see buildCategorySelect in activity-shared.js), same split as
// time-management's Settings page vs. its task form.

function textColorSelectElement(selected) {
  const select = Global.el("select", { "aria-label": "Text color" }, [
    Global.el("option", { value: "dark", text: "Dark text" }),
    Global.el("option", { value: "light", text: "Light text" }),
  ]);
  select.value = selected;
  return select;
}

// Live preview of what a real activity's summary row looks like with this
// category applied (see .item-card.has-category in style.css) - a colored
// swatch with the category name in the chosen text color, so you can judge
// contrast before saving rather than guessing and checking against a real
// activity card afterward.
function categoryPreviewRow() {
  return Global.el("span", { class: "category-preview-row", text: "Preview" });
}

function updateCategoryPreview(swatch, name, color, textColor) {
  swatch.textContent = name.trim() || "Preview";
  swatch.style.setProperty("--cat-color", color);
  swatch.style.setProperty("--cat-text-color", textColor === "light" ? "#ffffff" : "#000000");
}

// Every currently-rendered row's live input elements, keyed by category id
// - what "Save changes" below reads from. A row's fields are editable
// independently of every other row's, but nothing is sent to the server
// until you click that one button, so editing several rows in a row (e.g.
// flipping a bunch of text-color dropdowns after seeing them all rendered
// lighter - see the opacity change earlier) can't silently lose whichever
// rows you didn't happen to hit "Save" on individually, the way a
// per-row Save button did.
let categoryRowInputs = new Map();

// Six plain CSS dots rather than a font glyph (⋮⋮, ⣿, ...) - reliably
// crisp at this size regardless of the OS/browser's font rendering,
// instead of hoping a particular Unicode character is in every system
// font this could render with.
function dragHandleElement(category) {
  const handle = Global.el("div", {
    class: "category-drag-handle",
    "aria-label": `Drag to reorder "${category.name}"`,
    title: "Drag to reorder",
  });
  for (let i = 0; i < 6; i++) handle.appendChild(Global.el("span", { class: "category-drag-handle-dot" }));
  return handle;
}

function categoryRowElement(category) {
  const nameInput = Global.el("input", { type: "text", value: category.name });
  const colorInput = Global.el("input", { type: "color", value: category.color });
  const textColorSelect = textColorSelectElement(category.text_color);
  const preview = categoryPreviewRow();
  updateCategoryPreview(preview, category.name, category.color, category.text_color);
  for (const el of [nameInput, colorInput, textColorSelect]) {
    const refresh = () => updateCategoryPreview(preview, nameInput.value, colorInput.value, textColorSelect.value);
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  }
  categoryRowInputs.set(category.id, { category, nameInput, colorInput, textColorSelect });

  const dragHandle = dragHandleElement(category);

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete category "${category.name}"?`)) return;
      try {
        await Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, { method: "DELETE" });
        Global.showMessage(`Deleted "${category.name}".`, "success");
        await refreshCategoriesEverywhere();
      } catch (err) {
        // 409 from the backend when it's still assigned to an activity -
        // fetchJSON surfaces the response body's `detail` as err.message.
        Global.showMessage(err.message, "error");
      }
    },
  });

  const row = Global.el("div", { class: "category-row", "data-id": String(category.id) }, [
    dragHandle,
    colorInput,
    nameInput,
    textColorSelect,
    preview,
    deleteBtn,
  ]);
  wireCategoryDrag(dragHandle, row);
  return row;
}

// --- drag-to-reorder ---------------------------------------------------
//
// A plain vertical sortable list (Pointer Events, same as agenda.js, for
// the same mouse+touch-unification reason - native HTML5 drag-and-drop
// never fires from touch input at all). Deliberately simpler than
// agenda.js's drag, though: no floating ghost element, no drop-zone
// geometry - the dragged row just swaps position in the DOM directly as
// your pointer crosses a neighbor's midpoint (the classic minimal
// sortable-list algorithm, see rowAfterPointerY below), which is all a
// single vertical list needs. Reordering is structural, not a field edit
// like name/color/text color, so a drop commits immediately (one bulk
// request) rather than waiting on "Save changes" too - same
// immediate-on-drop precedent as Delete.

const CATEGORY_AUTO_SCROLL_EDGE_PX = 60;
const CATEGORY_AUTO_SCROLL_SPEED_PX = 14;

// Which row (if any) the dragged row should be inserted BEFORE, given the
// pointer's current Y - null means "after every row" (append at the end).
// The standard small "getDragAfterElement" pattern: each candidate row's
// own vertical center is compared against the pointer, and the row whose
// center is nearest above the pointer (i.e. offset is negative and
// largest) is the one to insert before.
function rowAfterPointerY(container, pointerY, draggingRow) {
  const rows = [...container.querySelectorAll(".category-row")].filter((r) => r !== draggingRow);
  let closest = { offset: -Infinity, row: null };
  for (const row of rows) {
    const box = row.getBoundingClientRect();
    const offset = pointerY - (box.top + box.height / 2);
    if (offset < 0 && offset > closest.offset) closest = { offset, row };
  }
  return closest.row;
}

function wireCategoryDrag(handle, row) {
  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0) return; // left click / primary touch only
    e.preventDefault();
    const container = row.parentElement;
    // Capture on the container, not the handle - the handle is a child of
    // `row`, which this drag physically moves (container.insertBefore)
    // every time it crosses a neighbor. Moving an element that currently
    // holds pointer capture is exactly what was cutting drags short after
    // one slot: some browsers drop capture as soon as the capturing
    // element (or its ancestor) gets reparented, firing lostpointercapture
    // mid-drag. The container itself never moves - only its children get
    // reordered - so capturing there is immune to that.
    container.setPointerCapture(e.pointerId);
    row.classList.add("category-row-dragging");

    let lastY = e.clientY;

    function reorderForPointer() {
      const target = rowAfterPointerY(container, lastY, row);
      if (target === row.nextElementSibling) return; // already there - avoid needless reflow
      if (target) container.insertBefore(row, target);
      else container.appendChild(row);
    }

    // The category list isn't in its own scrolling box (unlike agenda.js's
    // day columns) - Manage Categories can run longer than the viewport,
    // so this scrolls the whole page when the pointer nears the top/bottom
    // edge, the window-scroll equivalent of agenda.js's autoScrollNear.
    function autoScrollNear(y) {
      if (y < CATEGORY_AUTO_SCROLL_EDGE_PX) window.scrollBy(0, -CATEGORY_AUTO_SCROLL_SPEED_PX);
      else if (window.innerHeight - y < CATEGORY_AUTO_SCROLL_EDGE_PX) window.scrollBy(0, CATEGORY_AUTO_SCROLL_SPEED_PX);
    }

    // Run on every real pointermove (feels immediate) *and* every
    // animation frame for the drag's duration (so scrolling and
    // reordering both keep going while the pointer holds still near an
    // edge - content is moving under it even though the pointer isn't) -
    // same two-callers-one-function shape as agenda.js's updateDragState.
    function updateDragState() {
      autoScrollNear(lastY);
      reorderForPointer();
    }

    let rafId = requestAnimationFrame(function tick() {
      updateDragState();
      rafId = requestAnimationFrame(tick);
    });

    const onMove = (moveEvent) => {
      lastY = moveEvent.clientY;
      updateDragState();
    };
    // pointerup/pointercancel are the "normal" end-of-drag signals, but
    // aren't the only way capture can end (the pointer can be captured by
    // something else, or - seen during testing - a synthesized drag can
    // release the button without the expected pointerup ever reaching this
    // element). lostpointercapture fires whenever capture ends for *any*
    // reason, so it's the one actually-reliable signal to hang cleanup on;
    // the other two are kept too since they fire first in the normal case
    // and every listener here calls the same idempotent end() below.
    let ended = false;
    const end = async () => {
      if (ended) return;
      ended = true;
      cancelAnimationFrame(rafId);
      container.removeEventListener("pointermove", onMove);
      container.removeEventListener("pointerup", end);
      container.removeEventListener("pointercancel", end);
      container.removeEventListener("lostpointercapture", end);
      row.classList.remove("category-row-dragging");
      await commitCategoryOrder(container);
    };
    container.addEventListener("pointermove", onMove);
    container.addEventListener("pointerup", end);
    container.addEventListener("pointercancel", end);
    container.addEventListener("lostpointercapture", end);
  });
}

// Reads the current DOM order (already live-updated by the drag itself)
// and sends it as the new source of truth - see reorder_categories in
// crud.py, which resequences everyone to clean 10/20/30... values from
// this list rather than the client trying to compute a value that fits
// between two neighbors.
async function commitCategoryOrder(container) {
  const orderedIds = [...container.querySelectorAll(".category-row")].map((r) => Number(r.dataset.id));
  try {
    await Global.fetchJSON(`${CATEGORIES_API}/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_ids: orderedIds }),
    });
    await refreshCategoriesEverywhere();
  } catch (err) {
    Global.showMessage(err.message, "error");
    await refreshCategoriesEverywhere(); // snap back to the real server order
  }
}

// Sends one PATCH per row whose name/color/text_color actually changed
// since the last render (untouched rows are skipped - no need to re-save
// fields that are already correct). Reordering and deleting stay
// immediate (see reorderCategory / the Delete button above) - this button
// is only for the free-text/color fields, which you're much more likely
// to want to change several of in one pass.
async function saveCategoryChanges() {
  const changed = [];
  for (const { category, nameInput, colorInput, textColorSelect } of categoryRowInputs.values()) {
    const name = nameInput.value.trim();
    if (name && (name !== category.name || colorInput.value !== category.color || textColorSelect.value !== category.text_color)) {
      changed.push({ category, name, color: colorInput.value, text_color: textColorSelect.value });
    }
  }
  if (changed.length === 0) {
    Global.showMessage("No changes to save.", "success");
    return;
  }
  try {
    await Promise.all(
      changed.map(({ category, name, color, text_color }) =>
        Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, color, text_color }),
        })
      )
    );
    Global.showMessage(`Saved ${changed.length} categor${changed.length === 1 ? "y" : "ies"}.`, "success");
    await refreshCategoriesEverywhere();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

async function refreshCategoriesEverywhere() {
  await loadCategoriesCache();
  renderCategoryRows();
  // Category names/colors may have changed - rebuild every visible card
  // and select so nothing shows stale data without a full reload.
  await loadActivities();
}

function renderCategoryRows() {
  const container = document.getElementById("category-rows");
  container.innerHTML = "";
  categoryRowInputs = new Map();
  if (categories.length === 0) {
    container.appendChild(Global.el("p", { class: "note", text: "No categories yet - add one below." }));
    return;
  }
  for (const category of categories) container.appendChild(categoryRowElement(category));
}

function initCategoryManager() {
  renderCategoryRows();

  document.getElementById("save-category-changes-btn").addEventListener("click", saveCategoryChanges);

  const form = document.getElementById("add-category-form");
  const nameInput = document.getElementById("new-category-name");
  const colorInput = document.getElementById("new-category-color");
  const textColorSelect = document.getElementById("new-category-text-color");
  const preview = document.getElementById("new-category-preview");

  const refreshPreview = () => updateCategoryPreview(preview, nameInput.value, colorInput.value, textColorSelect.value);
  for (const el of [nameInput, colorInput, textColorSelect]) {
    el.addEventListener("input", refreshPreview);
    el.addEventListener("change", refreshPreview);
  }
  refreshPreview();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    try {
      await Global.fetchJSON(CATEGORIES_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, color: colorInput.value, text_color: textColorSelect.value }),
      });
      form.reset();
      colorInput.value = "#375a99";
      refreshPreview();
      Global.showMessage(`Added "${name}".`, "success");
      await refreshCategoriesEverywhere();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

function decodeBase64UrlPrefill(value) {
  try {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(value.length + ((4 - (value.length % 4)) % 4), "=");
    return JSON.parse(decodeURIComponent(escape(atob(padded))));
  } catch (e) {
    return null;
  }
}

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
  // Only the true "you have no activities at all" case, not "your city
  // filter matched nothing" - that's city-filtered-empty's job (see
  // renderActivityLists), a different message for a different situation.
  document.getElementById("empty-state").hidden = activeCount + doneCount + archivedCount !== 0 || cityFilter.size > 0;

  const doneSection = document.getElementById("done-activities-section");
  doneSection.hidden = doneCount === 0;
  document.getElementById("done-activities-summary-text").textContent = `${doneCount} done`;

  const archivedSection = document.getElementById("archived-activities-section");
  archivedSection.hidden = archivedCount === 0;
  document.getElementById("archived-activities-summary-text").textContent = `${archivedCount} archived`;
}

// The one onChanged handler for every activity card on this page - removes
// wherever the card currently is and re-places it based on the activity's
// current done/archived state, so toggling either (via the Archive button
// or the done checkbox) moves it into the right list immediately instead
// of needing a reload. Also the target of a plain edit-save/scrape refresh
// (activity-shared.js calls this before its own in-place replaceWith,
// which then becomes a harmless no-op on the now-detached old card).
function handleActivityChanged(updated) {
  // Keep the cached list (see loadedActivities above) in sync - it's what
  // renderActivityLists (below) re-renders from.
  const cacheIndex = loadedActivities.findIndex((a) => a.id === updated.id);
  if (cacheIndex >= 0) loadedActivities[cacheIndex] = updated;

  // A full re-render, not a targeted remove+replace - the edit may have
  // changed done/archived (needs a different list), category (may change
  // its position when sorted by category), or city (might now fail an
  // active filter entirely) - renderActivityLists is the one place all of
  // those are already handled correctly together. pendingEditActivityId
  // (normally the agenda ?edit= deep-link's job) is reused here just to
  // keep the just-saved card expanded, the same UX a direct replace used
  // to give for free.
  pendingEditActivityId = updated.id;
  renderActivityLists();
}

function placeActivityCard(activity, opts = {}) {
  const card = activityCardElement(activity, {
    showTripBadge: true,
    onDeleted: refreshActivityCounts,
    onChanged: handleActivityChanged,
    ...opts,
  });
  listForActivity(activity).appendChild(card);
  return card;
}

// The full activity list from the last fetch, and the current sort mode
// ("default" = whatever order the API returned, i.e. newest-created-first
// - "category" = grouped by category, in Manage Categories' own order, via
// sortActivitiesByCategory in common.js). Cached here rather than
// re-fetched on every sort change - switching modes is a pure client-side
// re-render of data already on hand.
let loadedActivities = [];
let activitySortMode = "default";
// City names (as-is, matching activity.city exactly) currently checked in
// the filter - empty means "show all". Not category ids like the agenda
// filter - there's no managed City table, just whatever strings are
// actually in use (see loadCitiesCache in activity-shared.js).
let cityFilter = new Set();

function renderActivityLists() {
  for (const id of ["activities-list", "done-activities-list", "archived-activities-list"]) {
    document.getElementById(id).innerHTML = "";
  }
  const filtered = cityFilter.size === 0 ? loadedActivities : loadedActivities.filter((a) => a.city && cityFilter.has(a.city));
  document.getElementById("city-filtered-empty").hidden = !(loadedActivities.length > 0 && filtered.length === 0);

  const ordered = activitySortMode === "category" ? sortActivitiesByCategory(filtered, categoriesById) : filtered;
  let editTarget = null;
  for (const activity of ordered) {
    // ?edit=<id> (see the "Edit" link on agenda.html's entries) lands
    // here with that one activity already expanded and in edit mode,
    // instead of you having to find and expand it yourself - only on the
    // render right after landing on the page, not every re-render a later
    // sort-mode change triggers (pendingEditActivityId is cleared below
    // once it's been used).
    const isEditTarget = activity.id === pendingEditActivityId;
    const card = placeActivityCard(activity, { expanded: isEditTarget, startInEdit: isEditTarget });
    if (isEditTarget) editTarget = card;
  }
  refreshActivityCounts();
  if (editTarget) editTarget.scrollIntoView({ block: "center" });
  // Cleared unconditionally, not just on a match - an edit that changes an
  // activity's city to something the active filter now excludes means it
  // never renders at all this pass, and a lingering id here would wrongly
  // auto-expand+scroll to it if it reappears on some later, unrelated
  // render (e.g. after the filter's cleared).
  pendingEditActivityId = null;
}

async function loadActivities() {
  loadedActivities = await Global.fetchJSON(ACTIVITIES_API);
  renderActivityLists();
}

// Multiselect of every city in use (see Global.buildMultiSelect in
// shared-assets' theme.js, and loadCitiesCache/cities in
// activity-shared.js) - so if you're heading back somewhere, you can
// filter straight down to "what did we not get to in Toronto."
function initCityFilter() {
  const mount = document.getElementById("city-filter-mount");
  mount.innerHTML = "";
  if (cities.length === 0) return; // nothing to filter by yet
  const widget = Global.buildMultiSelect({
    options: cities.map((c) => ({ value: c, label: c })),
    selected: [...cityFilter],
    placeholder: "All cities",
    onChange: (selected) => {
      cityFilter = new Set(selected);
      renderActivityLists();
    },
  });
  mount.appendChild(widget);
}

function initActivitySort() {
  const select = document.getElementById("activity-sort-select");
  select.value = activitySortMode;
  select.addEventListener("change", () => {
    activitySortMode = select.value;
    renderActivityLists();
  });
}

// --- distance tool ---------------------------------------------------------
//
// One shared backend endpoint (POST /api/activities/distance-matrix - see
// app/distance.py/routers/activities.py) behind two modes, picked purely by
// whether an anchor is chosen:
//  - No anchor: full pairwise distances among the selected candidates (e.g.
//    "which 2 of these 5 cafes are closest to each other").
//  - An anchor selected: distance from every OTHER candidate to just that
//    one (e.g. "which of these 3 restaurants is closest to the show").
// Real walking/driving distance via Google's Distance Matrix API, not a
// guess - see distance.py's module docstring for why that matters here.
let distanceCandidateIds = new Set();

function activityLabel(activity) {
  return activity.city ? `${activity.name} — ${activity.city}` : activity.name;
}

function initDistanceTool() {
  const candidatesMount = document.getElementById("distance-candidates-mount");
  const anchorSelect = document.getElementById("distance-anchor-select");
  candidatesMount.innerHTML = "";
  anchorSelect.innerHTML = '<option value="">None - compare candidates with each other</option>';

  if (loadedActivities.length === 0) return;

  const widget = Global.buildMultiSelect({
    options: loadedActivities.map((a) => ({ value: a.id, label: activityLabel(a) })),
    selected: [...distanceCandidateIds],
    placeholder: "Select activities",
    onChange: (selected) => {
      distanceCandidateIds = new Set(selected.map(Number));
    },
  });
  candidatesMount.appendChild(widget);

  for (const activity of loadedActivities) {
    anchorSelect.appendChild(Global.el("option", { value: String(activity.id), text: activityLabel(activity) }));
  }

  document.getElementById("distance-calculate-btn").addEventListener("click", runDistanceComparison);
}

function formatDistancePair(pair, fromLabel, toLabel) {
  if (pair.skipped_reason) {
    const reason = pair.skipped_reason === "no address" ? "no address on file" : "no route found";
    return Global.el("li", { class: "distance-result-skipped", text: `${fromLabel} → ${toLabel}: ${reason}` });
  }
  return Global.el("li", {}, [
    Global.el("span", { class: "distance-result-names", text: `${fromLabel} → ${toLabel}` }),
    Global.el("span", { class: "distance-result-value", text: `${pair.distance_text} · ${pair.duration_text}` }),
  ]);
}

async function runDistanceComparison() {
  const resultsEl = document.getElementById("distance-results");
  const anchorValue = document.getElementById("distance-anchor-select").value;
  const anchorId = anchorValue ? Number(anchorValue) : null;
  const mode = document.getElementById("distance-mode-select").value;
  const forceRefresh = document.getElementById("distance-force-refresh").checked;
  const candidateIds = [...distanceCandidateIds].filter((id) => id !== anchorId);
  const activitiesById = Object.fromEntries(loadedActivities.map((a) => [a.id, a]));

  if (candidateIds.length === 0) {
    Global.showMessage("Select at least one candidate activity.", "error");
    return;
  }
  if (!anchorId && candidateIds.length < 2) {
    Global.showMessage("Select at least 2 candidates to compare against each other, or pick something to compare against.", "error");
    return;
  }

  resultsEl.innerHTML = "";
  resultsEl.appendChild(Global.el("p", { class: "note", text: "Calculating…" }));

  try {
    const body = anchorId
      ? { origin_ids: candidateIds, destination_ids: [anchorId], mode, force_refresh: forceRefresh }
      : { origin_ids: candidateIds, destination_ids: candidateIds, mode, force_refresh: forceRefresh };
    const { pairs } = await Global.fetchJSON(`${ACTIVITIES_API}/distance-matrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    // Full-pairwise mode returns both directions (A→B and B→A) - walking/
    // driving distance isn't always symmetric (one-way streets, etc.), so
    // showing both as if they were two different facts would be more
    // confusing than useful here - keep one entry per unordered pair.
    // Prefer whichever direction actually resolved rather than always
    // picking (say) the lower-id-first one regardless - Google's routing
    // can itself be asymmetric (a path only walkable one way), and always
    // keeping the same arbitrary direction could throw away the one side
    // that actually had a real result in favor of a "no route found" from
    // the other.
    let deduped = pairs;
    if (!anchorId) {
      const byPairKey = new Map();
      for (const pair of pairs) {
        const key = [pair.origin_id, pair.destination_id].sort((a, b) => a - b).join(":");
        const existing = byPairKey.get(key);
        if (!existing || (existing.skipped_reason && !pair.skipped_reason)) byPairKey.set(key, pair);
      }
      deduped = [...byPairKey.values()];
    }
    const sortable = deduped.filter((p) => !p.skipped_reason);
    const skipped = deduped.filter((p) => p.skipped_reason);
    sortable.sort((a, b) => a.distance_meters - b.distance_meters);

    resultsEl.innerHTML = "";
    if (sortable.length === 0 && skipped.length === 0) {
      resultsEl.appendChild(Global.el("p", { class: "note", text: "Nothing to compare." }));
      return;
    }
    const list = Global.el("ul", { class: "distance-result-list" });
    for (const pair of [...sortable, ...skipped]) {
      const fromLabel = activityLabel(activitiesById[pair.origin_id]);
      const toLabel = activityLabel(activitiesById[pair.destination_id]);
      list.appendChild(formatDistancePair(pair, fromLabel, toLabel));
    }
    if (sortable.length) list.firstElementChild.classList.add("distance-result-closest");
    resultsEl.appendChild(list);
  } catch (err) {
    resultsEl.innerHTML = "";
    Global.showMessage(err.message, "error");
  }
}

const pageParams = new URLSearchParams(window.location.search);
const prefillParam = pageParams.get("prefill");
const prefill = prefillParam ? decodeBase64UrlPrefill(prefillParam) : null;
const editIdParam = pageParams.get("edit");
let pendingEditActivityId = editIdParam ? Number(editIdParam) : null;
if (prefillParam || editIdParam) {
  // Drop these from the URL so refreshing the page doesn't re-open the
  // form (with possibly now-stale prefill data) or re-jump-to-edit again.
  const url = new URL(window.location.href);
  url.searchParams.delete("prefill");
  url.searchParams.delete("edit");
  window.history.replaceState({}, "", url);
}

async function init() {
  // Categories have to be loaded before anything that builds a category
  // <select> (the add form below, and every activity card/edit-pane) -
  // otherwise those selects would render with no options and never pick
  // up categories that show up after the fact.
  await loadCategoriesCache();
  await loadCitiesCache();

  initAddActivityToggle(document.getElementById("add-activity-container"), {
    tripId: null,
    prefill,
    autoOpen: !!prefill,
    onCreated: (created) => {
      loadedActivities.push(created);
      // A full re-render, not a direct placeActivityCard append - a filter
      // may be active, and the new activity might not match it (wrong
      // city). renderActivityLists re-applies both the filter and the
      // current sort mode rather than unconditionally showing it.
      renderActivityLists();
    },
  });
  initCategoryManager();
  initActivitySort();
  initCityFilter();

  if (prefill) Global.showMessage(`Filled in from ${prefill.url ? Global.domainFromUrl(prefill.url) || "clipped page" : "clipped page"} - review and save.`, "success");

  await loadActivities();
  // After loadActivities, not before - the candidates/anchor pickers are
  // built from loadedActivities, which loadActivities is what populates.
  initDistanceTool();
}

init().catch((err) => Global.showMessage(err.message, "error"));
