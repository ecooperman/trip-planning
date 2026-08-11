// Standalone activities page - lists every activity (associated or not)
// and lets you create one without a trip. Uses the exact same form/card
// code (activity-shared.js) as the activities section on trip.html; the
// only difference is no tripId is passed, so nothing auto-associates.

function refreshActivityCounts() {
  const count = document.querySelectorAll("#activities-list .item-card").length;
  document.getElementById("activity-count").textContent = count ? `${count}` : "";
  document.getElementById("empty-state").hidden = count !== 0;
}

async function loadActivities() {
  const list = document.getElementById("activities-list");
  list.innerHTML = "";
  const activities = await fetchJSON(ACTIVITIES_API);
  for (const activity of activities) {
    list.appendChild(
      activityCardElement(activity, {
        showTripBadge: true,
        onDeleted: refreshActivityCounts,
      })
    );
  }
  refreshActivityCounts();
}

initAddActivityToggle(document.getElementById("add-activity-container"), {
  tripId: null,
  onCreated: (created) => {
    document.getElementById("activities-list").appendChild(
      activityCardElement(created, { expanded: true, showTripBadge: true, onDeleted: refreshActivityCounts })
    );
    refreshActivityCounts();
  },
});

loadActivities().catch((err) => showMessage(err.message, "error"));
