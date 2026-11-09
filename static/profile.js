// Profile (profile.html): the signed-in person's own API keys. The server never
// sends a key back - only whether there is one and its last four characters - so
// this page can save, replace and remove but never show one.

const KEYS_API = "/api/profile/api-keys";
const keysEl = document.getElementById("api-keys");

function statusLine(k) {
  if (k.has_own_key && !k.own_key_readable) {
    return { text: "Your saved key can't be read any more - please enter it again.", warn: true };
  }
  if (k.has_own_key) {
    const when = k.added_at ? ` (added ${new Date(`${k.added_at}Z`).toLocaleDateString()})` : "";
    return { text: `Using your key ending ${k.last4}${when}.`, warn: false };
  }
  if (k.using_house_key) return { text: "Using the server's own key, because you're the administrator.", warn: false };
  return { text: `Not set - ${k.feature.toLowerCase()} is turned off for you.`, warn: false };
}

async function save(k, input, buttons) {
  const key = input.value.trim();
  if (!key) return;
  buttons.forEach((b) => (b.disabled = true));
  try {
    const result = await Global.fetchJSON(`${KEYS_API}/${k.provider}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    input.value = "";
    Global.showMessage(result.note || `Saved your ${k.label} key.`, result.verified === false || result.note ? "error" : "success");
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
  load();
}

async function remove(k, buttons) {
  if (!confirm(`Remove your ${k.label} key? ${k.feature} will stop working for you until you add another.`)) return;
  buttons.forEach((b) => (b.disabled = true));
  try {
    await Global.fetchJSON(`${KEYS_API}/${k.provider}`, { method: "DELETE" });
    Global.showMessage(`Removed your ${k.label} key.`, "success");
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
  load();
}

function keyCard(k, canSave) {
  const status = statusLine(k);
  const input = Global.el("input", {
    type: "password",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: k.has_own_key ? "Paste a new key to replace it" : "Paste your key",
    "aria-label": `${k.label} API key`,
  });
  const saveBtn = Global.el("button", { type: "button", class: "save-btn", text: "Save and check" });
  const buttons = [saveBtn];
  const actions = [saveBtn];
  if (k.has_own_key) {
    const removeBtn = Global.el("button", { type: "button", class: "cancel-btn", text: "Remove" });
    removeBtn.addEventListener("click", () => remove(k, buttons));
    buttons.push(removeBtn);
    actions.push(removeBtn);
  }
  saveBtn.addEventListener("click", () => save(k, input, buttons));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      save(k, input, buttons);
    }
  });

  const heading = [Global.el("h3", { text: k.label })];
  if (k.optional) heading.push(Global.el("span", { class: "item-badge item-badge-muted", text: "Optional" }));

  return Global.el("div", { class: "key-card" }, [
    Global.el("div", { class: "key-card-head" }, heading),
    Global.el("p", { class: "field-hint", text: k.description }),
    Global.el("p", { class: "key-status" + (status.warn ? " warn" : (k.usable ? " ok" : "")), text: status.text }),
    canSave
      ? Global.el("div", { class: "key-form" }, [input, ...actions])
      : Global.el("p", { class: "field-hint", text: "Saving keys isn't set up on the server yet - ask the administrator." }),
    Global.el("a", { href: k.get_url, target: "_blank", rel: "noopener noreferrer", class: "field-hint key-get", text: `Where to get a ${k.label} key →` }),
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
  keysEl.replaceChildren(...data.keys.map((k) => keyCard(k, data.can_save)));
}

Global.currentUser().then((me) => {
  if (me) document.getElementById("profile-email").textContent = me.email + (me.is_admin ? " - administrator" : "");
});
load();
