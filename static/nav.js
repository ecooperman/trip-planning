// Single source of truth for the bottom nav bar, injected into a
// <div id="app-nav-mount"></div> placeholder on every page - so a nav
// change (adding the Refresh button, say) is one file to edit instead of
// four. Mirrors icons.js's "single registry, applied at load" pattern.
// Needs `el` (common.js) and `applyIcons` (icons.js) already loaded.

function currentNavActive() {
  const path = window.location.pathname;
  if (path === "/activities.html") return "activities";
  // "/", "/trip.html", and "/agenda.html" are all trip-context pages.
  return "trips";
}

function renderAppNav() {
  const mount = document.getElementById("app-nav-mount");
  if (!mount) return;

  const active = currentNavActive();
  const nav = el("nav", { class: "app-nav" }, [
    el("a", { href: "/", class: "app-nav-link" + (active === "trips" ? " active" : "") }, [
      el("span", { class: "app-nav-icon", "data-icon": "compass", "aria-hidden": "true" }),
      "Trips",
    ]),
    el("a", { href: "/activities.html", class: "app-nav-link" + (active === "activities" ? " active" : "") }, [
      el("span", { class: "app-nav-icon", "data-icon": "list", "aria-hidden": "true" }),
      "Activities",
    ]),
    el("button", { type: "button", class: "app-nav-link", onclick: () => location.reload() }, [
      el("span", { class: "app-nav-icon", "data-icon": "refresh", "aria-hidden": "true" }),
      "Refresh",
    ]),
  ]);

  mount.replaceWith(nav);
  applyIcons(nav);
}

renderAppNav();
