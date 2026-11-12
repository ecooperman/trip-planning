// Users (users.html, administrator only): everyone with an account in Trips, with what
// they own; add someone, remove (and restore) their access, or delete a removed
// person's data. The server refuses all of it to anyone else (403).

const activeEl = document.getElementById("active-users");
const removedEl = document.getElementById("removed-section");
const removedList = document.getElementById("removed-users");
const addEl = document.getElementById("add-user");

const api = (path, method = "GET") => Global.fetchJSON(`/api/admin/users${path}`, { method });
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function describe(u) {
  const parts = [`joined ${u.created_at ? new Date(`${u.created_at}Z`).toLocaleDateString() : "before accounts were tracked"}`];
  parts.push(u.owned_trips ? `owns ${plural(u.owned_trips, "trip")}` : "owns no trips");
  if (u.shared_with_them) parts.push(`on ${plural(u.shared_with_them, "shared trip")}`);
  if (u.activities) parts.push(plural(u.activities, "activity").replace("activitys", "activities"));
  if (u.places) parts.push(plural(u.places, "place"));
  return parts.join(" - ");
}

async function act(button, request, success) {
  button.disabled = true;
  try {
    await request();
    Global.showMessage(success, "success");
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
  load();
}

function revoke(u, button) {
  if (
    !confirm(
      `Remove ${u.email}'s access to Trips?\n\nThey won't be able to use it, but nothing of theirs is deleted and you can restore them any time. Other apps are not affected.`
    )
  )
    return;
  act(button, () => api(`/${u.id}/revoke`, "POST"), `${u.email} can no longer use Trips.`);
}

function restore(u, button) {
  act(button, () => api(`/${u.id}/restore`, "POST"), `${u.email} has access again.`);
}

function destroy(u, button) {
  const owned = [];
  if (u.owned_trips) owned.push(plural(u.owned_trips, "trip"));
  if (u.activities) owned.push(u.activities === 1 ? "1 activity" : `${u.activities} activities`);
  if (u.places) owned.push(plural(u.places, "place"));
  if (u.categories) owned.push(u.categories === 1 ? "1 category" : `${u.categories} categories`);
  let text = owned.length
    ? `Permanently delete ${u.email}'s account data?\n\nThis erases ${owned.join(", ")}, along with their saved API keys.`
    : `Permanently delete ${u.email}'s account data?\n\nThey own nothing, so this only clears their place on other people's trips, their saved API keys and the invites they made.`;
  if (u.people_on_their_trips) {
    text += `\n\n${plural(u.people_on_their_trips, "other person").replace("persons", "people")} can see those trips and will lose them too.`;
  }
  text += "\n\nThis can't be undone. Their email stays here as removed.";
  if (!confirm(text)) return;
  act(button, () => api(`/${u.id}`, "DELETE"), `Deleted what ${u.email} owned.`);
}

function card(u) {
  const badges = [];
  if (u.is_admin) badges.push(Global.el("span", { class: "item-badge item-badge-accent", text: "Administrator" }));
  if (u.status === "removed") badges.push(Global.el("span", { class: "item-badge item-badge-muted", text: "Removed" }));
  const title = Global.el("div", {}, [Global.el("strong", { text: u.email + " " }), ...badges]);

  const actions = [];
  if (u.status === "active" && !u.is_admin) {
    const b = Global.el("button", { type: "button", class: "cancel-btn", text: "Remove access" });
    b.addEventListener("click", () => revoke(u, b));
    actions.push(b);
  }
  if (u.status === "removed") {
    const restoreBtn = Global.el("button", { type: "button", class: "secondary-btn", text: "Restore" });
    restoreBtn.addEventListener("click", () => restore(u, restoreBtn));
    const del = Global.el("button", { type: "button", class: "danger-btn", text: "Delete account data" });
    del.addEventListener("click", () => destroy(u, del));
    actions.push(restoreBtn, del);
  }
  return Global.el("div", { class: "request-card" }, [
    Global.el("div", { class: "request-info" }, [title, Global.el("div", { class: "field-hint", text: describe(u) })]),
    Global.el("div", { class: "request-actions" }, actions),
  ]);
}

async function load() {
  let users;
  try {
    users = await Global.withLoading(activeEl, api(""));
  } catch (err) {
    activeEl.replaceChildren(Global.el("p", { class: "field-hint", text: err.message }));
    return;
  }
  const active = users.filter((u) => u.status === "active");
  const removed = users.filter((u) => u.status === "removed");
  activeEl.replaceChildren(
    ...(active.length ? active.map(card) : [Global.el("p", { class: "field-hint", text: "Nobody has access yet." })])
  );
  removedEl.classList.toggle("hidden", removed.length === 0);
  removedList.replaceChildren(...removed.map(card));
}

// Add someone (the same box as the invite page: not a sign-in field, so password managers stay out).
(function mountAdd() {
  const input = Global.el("input", {
    type: "email",
    placeholder: "Email address",
    autocomplete: "off",
    "data-1p-ignore": "",
    "data-lpignore": "true",
    "data-bwignore": "true",
    "data-form-type": "other",
    "aria-label": "Email address of someone to let into Trips",
  });
  const button = Global.el("button", { type: "button", class: "secondary-btn", text: "Add" });
  const problem = Global.el("p", { class: "field-hint is-error hidden" });
  addEl.replaceChildren(Global.el("div", { class: "member-add" }, [input, button]), problem);

  const show = (text) => {
    problem.textContent = text || "";
    problem.classList.toggle("hidden", !text);
  };
  async function add() {
    const email = input.value.trim();
    if (!email) return;
    show("");
    button.disabled = true;
    try {
      const user = await Global.fetchJSON("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      input.value = "";
      Global.showMessage(`${user.email} can now sign in to Trips.`, "success");
      load();
    } catch (err) {
      show(err.message);
    }
    button.disabled = false;
  }
  button.addEventListener("click", add);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    }
  });
  input.addEventListener("input", () => show(""));
})();

load();
