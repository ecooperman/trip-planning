// Single source of truth for the bottom nav bar, injected into a
// <div id="app-nav-mount"></div> placeholder on every page - so a nav
// change (adding the Refresh button, say) is one file to edit instead of
// four. This app's own version of this pattern was generalized into
// Global.buildNav (theme.js) - only the app-specific "which page is
// active" list lives here now.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/activities.html") return "activities";
  // "/", "/trip.html", and "/agenda.html" are all trip-context pages.
  return "trips";
}

const active = currentNavActive();
Global.buildNav([
  { href: "/", icon: "compass", label: "Trips", active: active === "trips" },
  { href: "/activities.html", icon: "list", label: "Activities", active: active === "activities" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);
