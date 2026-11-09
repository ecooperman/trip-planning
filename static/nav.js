// Single source of truth for the bottom nav bar, injected into a
// <div id="app-nav-mount"></div> placeholder on every page - so a nav
// change (adding the Refresh button, say) is one file to edit instead of
// four. This app's own version of this pattern was generalized into
// Global.buildNav (theme.js) - only the app-specific "which page is
// active" list lives here now.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/activities.html") return "activities";
  if (path === "/places.html") return "places";
  if (path === "/invites.html") return "invites"; // no tab of its own: none lit
  // "/", "/trip.html", and "/agenda.html" are all trip-context pages.
  return "trips";
}

const active = currentNavActive();
Global.buildNav([
  { href: "/", icon: "compass", label: "Trips", active: active === "trips" },
  { href: "/activities.html", icon: "list", label: "Activities", active: active === "activities" },
  // No dedicated map-pin icon exists in shared-assets yet - "tag" reused
  // pragmatically rather than adding one there for a single app's sake;
  // worth a real icon if this bar gets revisited generally.
  { href: "/places.html", icon: "tag", label: "Places", active: active === "places" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);

// The administrator also gets the Invites page, with how many requests are
// waiting for them (the badge is kept current by invites.js).
Global.currentUser().then((me) => {
  const nav = document.querySelector(".app-nav");
  if (!me || !me.is_admin || !nav) return;
  const waiting = me.pending_invites || 0;
  const count = Global.el("span", {
    id: "nav-invite-count",
    class: "item-badge item-badge-accent nav-count" + (waiting ? "" : " hidden"),
    text: String(waiting),
  });
  const link = Global.el(
    "a",
    { href: "/invites.html", class: "app-nav-link" + (location.pathname === "/invites.html" ? " active" : "") },
    [Global.el("span", { class: "app-nav-icon", "data-icon": "settings", "aria-hidden": "true" }), "Invites", count]
  );
  nav.insertBefore(link, nav.lastElementChild); // ahead of Refresh, which stays last
  applyIcons(link);
});

// Who's signed in, with a Log out link, in the page header (shared-assets).
Global.mountUserBadge(undefined, { profileHref: "/profile.html" });
