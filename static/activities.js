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

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("Category name is required.", "error");
        return;
      }
      try {
        await Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, color: colorInput.value, text_color: textColorSelect.value }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        await refreshCategoriesEverywhere();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

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

  return Global.el("div", { class: "category-row" }, [colorInput, nameInput, textColorSelect, preview, saveBtn, deleteBtn]);
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
  if (categories.length === 0) {
    container.appendChild(Global.el("p", { class: "note", text: "No categories yet - add one below." }));
    return;
  }
  for (const category of categories) container.appendChild(categoryRowElement(category));
}

function initCategoryManager() {
  renderCategoryRows();

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

async function loadActivities() {
  for (const id of ["activities-list", "done-activities-list", "archived-activities-list"]) {
    document.getElementById(id).innerHTML = "";
  }
  const activities = await Global.fetchJSON(ACTIVITIES_API);
  let editTarget = null;
  for (const activity of activities) {
    // ?edit=<id> (see the "Edit" link on agenda.html's entries) lands
    // here with that one activity already expanded and in edit mode,
    // instead of you having to find and expand it yourself.
    const isEditTarget = activity.id === editActivityId;
    const card = placeActivityCard(activity, { expanded: isEditTarget, startInEdit: isEditTarget });
    if (isEditTarget) editTarget = card;
  }
  refreshActivityCounts();
  if (editTarget) editTarget.scrollIntoView({ block: "center" });
}

const pageParams = new URLSearchParams(window.location.search);
const prefillParam = pageParams.get("prefill");
const prefill = prefillParam ? decodeBase64UrlPrefill(prefillParam) : null;
const editIdParam = pageParams.get("edit");
const editActivityId = editIdParam ? Number(editIdParam) : null;
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
      placeActivityCard(created, { expanded: true });
      refreshActivityCounts();
    },
  });
  initCategoryManager();

  if (prefill) Global.showMessage(`Filled in from ${prefill.url ? Global.domainFromUrl(prefill.url) || "clipped page" : "clipped page"} - review and save.`, "success");

  await loadActivities();
}

init().catch((err) => Global.showMessage(err.message, "error"));
