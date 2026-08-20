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

function decodeBase64UrlPrefill(value) {
  try {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(value.length + ((4 - (value.length % 4)) % 4), "=");
    return JSON.parse(decodeURIComponent(escape(atob(padded))));
  } catch (e) {
    return null;
  }
}

function refreshActivityCounts() {
  const count = document.querySelectorAll("#activities-list .item-card").length;
  document.getElementById("activity-count").textContent = count ? `${count}` : "";
  document.getElementById("empty-state").hidden = count !== 0;
}

async function loadActivities() {
  const list = document.getElementById("activities-list");
  list.innerHTML = "";
  const activities = await Global.fetchJSON(ACTIVITIES_API);
  let editTarget = null;
  for (const activity of activities) {
    // ?edit=<id> (see the "Edit" link on agenda.html's entries) lands
    // here with that one activity already expanded and in edit mode,
    // instead of you having to find and expand it yourself.
    const card = activityCardElement(activity, {
      showTripBadge: true,
      onDeleted: refreshActivityCounts,
      expanded: activity.id === editActivityId,
      startInEdit: activity.id === editActivityId,
    });
    list.appendChild(card);
    if (activity.id === editActivityId) editTarget = card;
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

initAddActivityToggle(document.getElementById("add-activity-container"), {
  tripId: null,
  prefill,
  autoOpen: !!prefill,
  onCreated: (created) => {
    document.getElementById("activities-list").appendChild(
      activityCardElement(created, { expanded: true, showTripBadge: true, onDeleted: refreshActivityCounts })
    );
    refreshActivityCounts();
  },
});

if (prefill) Global.showMessage(`Filled in from ${prefill.url ? Global.domainFromUrl(prefill.url) || "clipped page" : "clipped page"} - review and save.`, "success");

loadActivities().catch((err) => Global.showMessage(err.message, "error"));
