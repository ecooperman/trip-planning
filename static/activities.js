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

function categoryRowElement(category, { isFirst, isLast }) {
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

  // Reordering is structural, not a field edit like name/color/text color
  // above - it takes effect immediately (a PATCH per button click), the
  // same way Delete does, rather than waiting on "Save changes" too.
  const moveUpBtn = Global.el("button", {
    type: "button",
    class: "icon-btn",
    "aria-label": `Move "${category.name}" up`,
    title: "Move up",
    text: "▲",
    onclick: () => reorderCategory(category, -1),
  });
  const moveDownBtn = Global.el("button", {
    type: "button",
    class: "icon-btn",
    "aria-label": `Move "${category.name}" down`,
    title: "Move down",
    text: "▼",
    onclick: () => reorderCategory(category, 1),
  });
  // Set as a property, not an attrs["disabled"] value passed to
  // Global.el() - "disabled" is presence-based like "checked" (see
  // activity-shared.js's doneCheckbox comment), so disabled: false would
  // still render disabled="false" and permanently disable the button.
  moveUpBtn.disabled = isFirst;
  moveDownBtn.disabled = isLast;
  const reorderBtns = Global.el("div", { class: "category-row-reorder" }, [moveUpBtn, moveDownBtn]);

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

  return Global.el("div", { class: "category-row" }, [reorderBtns, colorInput, nameInput, textColorSelect, preview, deleteBtn]);
}

// Swaps this category's sort_order with its immediate neighbor in the
// current list (direction -1 = up, +1 = down) - the same "just touch the
// two rows involved" swap time-management's Task drag-reorder relies on,
// just triggered by a button instead of a drag since this list is short
// and a full drag-and-drop rig (see agenda.js) would be a lot of new
// machinery for a dozen rows you reorder rarely.
async function reorderCategory(category, direction) {
  const index = categories.findIndex((c) => c.id === category.id);
  const neighbor = categories[index + direction];
  if (!neighbor) return;
  try {
    await Promise.all([
      Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sort_order: neighbor.sort_order }),
      }),
      Global.fetchJSON(`${CATEGORIES_API}/${neighbor.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sort_order: category.sort_order }),
      }),
    ]);
    await refreshCategoriesEverywhere();
  } catch (err) {
    Global.showMessage(err.message, "error");
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
  categories.forEach((category, index) => {
    container.appendChild(categoryRowElement(category, { isFirst: index === 0, isLast: index === categories.length - 1 }));
  });
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
  document.getElementById("empty-state").hidden = activeCount + doneCount + archivedCount !== 0;

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
  const oldCard = document.querySelector(`#activities-list .item-card[data-id="${updated.id}"], #done-activities-list .item-card[data-id="${updated.id}"], #archived-activities-list .item-card[data-id="${updated.id}"]`);
  if (oldCard) oldCard.remove();
  placeActivityCard(updated, { expanded: true });
  refreshActivityCounts();
  // Keep the cached list (see loadedActivities above) in sync too - it's
  // what a later sort-mode change re-renders from, so a stale entry here
  // would make the update look like it reverted the moment you switched
  // sort modes.
  const cacheIndex = loadedActivities.findIndex((a) => a.id === updated.id);
  if (cacheIndex >= 0) loadedActivities[cacheIndex] = updated;
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

function renderActivityLists() {
  for (const id of ["activities-list", "done-activities-list", "archived-activities-list"]) {
    document.getElementById(id).innerHTML = "";
  }
  const ordered = activitySortMode === "category" ? sortActivitiesByCategory(loadedActivities, categoriesById) : loadedActivities;
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
  if (editTarget) {
    editTarget.scrollIntoView({ block: "center" });
    pendingEditActivityId = null;
  }
}

async function loadActivities() {
  loadedActivities = await Global.fetchJSON(ACTIVITIES_API);
  renderActivityLists();
}

function initActivitySort() {
  const select = document.getElementById("activity-sort-select");
  select.value = activitySortMode;
  select.addEventListener("change", () => {
    activitySortMode = select.value;
    renderActivityLists();
  });
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

  initAddActivityToggle(document.getElementById("add-activity-container"), {
    tripId: null,
    prefill,
    autoOpen: !!prefill,
    onCreated: (created) => {
      loadedActivities.push(created);
      placeActivityCard(created, { expanded: true });
      refreshActivityCounts();
    },
  });
  initCategoryManager();
  initActivitySort();

  if (prefill) Global.showMessage(`Filled in from ${prefill.url ? Global.domainFromUrl(prefill.url) || "clipped page" : "clipped page"} - review and save.`, "success");

  await loadActivities();
}

init().catch((err) => Global.showMessage(err.message, "error"));
