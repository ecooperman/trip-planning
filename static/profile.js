// Profile (profile.html): which services the signed-in person can use here. The keys themselves are saved once on the dashboard's Your profile
// page and used by every app; this page only says what is set, and never sees a key.

const KEYS_API = "/api/profile/api-keys";
const keysEl = document.getElementById("api-keys");

(function linkToTheDashboard() {
  const home = Global.dashboardUrl && Global.dashboardUrl();
  const link = document.getElementById("manage-keys");
  if (home) link.href = `${home}profile.html#keys-section`;
  else link.classList.add("hidden");
})();

function statusLine(k) {
  if (k.has_own_key) {
    const when = k.added_at ? ` (saved ${new Date(k.added_at).toLocaleDateString()})` : "";
    return { text: `Using your key ending ${k.last4}${when}.`, cls: " ok" };
  }
  if (k.using_house_key) return { text: "Using the server's own key, because you're the administrator. Usage is billed to the server's account.", cls: " house" };
  return { text: `Not set - ${k.feature.toLowerCase()} is turned off for you.`, cls: "" };
}

function keyCard(k) {
  const status = statusLine(k);
  const heading = [Global.el("h3", { text: k.label })];
  if (k.optional) heading.push(Global.el("span", { class: "item-badge item-badge-muted", text: "Optional" }));
  return Global.el("div", { class: "key-card" }, [
    Global.el("div", { class: "key-card-head" }, heading),
    Global.el("p", { class: "field-hint", text: k.description }),
    Global.el("p", { class: "key-status" + status.cls, text: status.text }),
  ]);
}

async function load() {
  let data;
  try {
    data = await Global.withLoading(keysEl, Global.fetchJSON(KEYS_API));
  } catch (err) {
    keysEl.replaceChildren(Global.el("p", { class: "field-hint", text: err.message }));
    return;
  }
  const cards = data.keys.map(keyCard);
  // An administrator can be running on the server's keys without noticing: say so up top.
  const onHouse = data.keys.filter((k) => k.using_house_key).map((k) => k.label);
  if (onHouse.length) {
    cards.unshift(
      Global.el("div", {
        class: "key-banner",
        text: `You're the administrator, so ${onHouse.join(", ")} ${onHouse.length === 1 ? "is" : "are"} running on the server's own key. Save your own key on your Brassworks profile to use your account instead.`,
      })
    );
  }
  keysEl.replaceChildren(...cards);
}

Global.currentUser().then((me) => {
  if (me) document.getElementById("profile-email").textContent = me.email + (me.is_admin ? " - administrator" : "");
});
load();
