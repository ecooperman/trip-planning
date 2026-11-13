// Single source of truth for the nav, injected by Global.buildNav (theme.js) -
// a nav change (adding the Refresh button, say) is one file to edit instead of
// every page's copy. Only the app-specific "which page is active" list lives
// here. Needs Global.buildNav and applyIcons already loaded.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/activities.html") return "activities";
  if (path === "/places.html") return "places";
  // "/", "/trip.html", "/agenda.html" and "/compare.html" are all trip-context pages.
  return "trips";
}

const active = currentNavActive();
const here = (path) => location.pathname === path;

// Built straight away, then rebuilt once we know who is signed in: everyone
// gets Invites (to ask for someone to be let in); the administrator also sees
// how many requests are waiting (kept current by invites.js) and gets the
// Users page. Groups only show in the sidebar layout.
function buildTripsNav(me) {
  const admin = !!(me && me.is_admin);
  const items = [
    { href: "/", icon: "compass", label: "Trips", active: active === "trips" && !here("/invites.html") && !here("/users.html") },
    { href: "/activities.html", icon: "list", label: "Activities", active: active === "activities" },
    // No dedicated map-pin icon exists in shared-assets yet - "tag" reused
    // pragmatically rather than adding one there for a single app's sake.
    { href: "/places.html", icon: "tag", label: "Places", active: active === "places" },
  ];
  if (me) {
    items.push({
      href: "/invites.html",
      icon: "settings",
      label: "Invites",
      active: here("/invites.html"),
      group: "Access",
      badge: admin ? { id: "nav-invite-count", count: me.pending_invites || 0 } : null,
    });
  }
  if (admin) items.push({ href: "/users.html", icon: "person", label: "Users", active: here("/users.html"), group: "Access" });
  items.push({ icon: "refresh", label: "Refresh", onclick: () => location.reload() });
  Global.buildNav(items);
}

buildTripsNav(null);
Global.currentUser().then((me) => {
  if (me) buildTripsNav(me);
});

// Who's signed in, with a Log out link, in the page header (shared-assets).
Global.mountUserBadge(undefined, { profileHref: "/profile.html" });
