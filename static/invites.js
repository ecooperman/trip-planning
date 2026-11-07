// The administrator's queue of requests to let new people in. The server
// refuses everyone else (403), which this page shows rather than a blank list.

const requestsEl = document.getElementById("invite-requests");
const ROLE_TEXT = { edit: "can edit", view: "can view" };

function updateNavCount(count) {
  const badge = document.getElementById("nav-invite-count");
  if (!badge) return;
  badge.textContent = String(count);
  badge.classList.toggle("hidden", count === 0);
}

async function decide(invite, action, buttons) {
  buttons.forEach((b) => (b.disabled = true));
  try {
    await Global.fetchJSON(`/api/admin/invites/${invite.id}/${action}`, { method: "POST" });
    Global.showMessage(
      action === "approve" ? `${invite.email} can now sign in and was added to "${invite.trip_name}".` : `Declined ${invite.email}.`,
      "success"
    );
  } catch (err) {
    // e.g. Cloudflare refused: the request stays in the queue.
    Global.showMessage(err.message, "error");
  }
  load();
}

function requestCard(invite) {
  const approve = Global.el("button", { type: "button", class: "save-btn", text: "Approve" });
  const decline = Global.el("button", { type: "button", class: "cancel-btn", text: "Decline" });
  const buttons = [approve, decline];
  approve.addEventListener("click", () => decide(invite, "approve", buttons));
  decline.addEventListener("click", () => decide(invite, "decline", buttons));

  const asked = new Date(`${invite.created_at}Z`).toLocaleString();
  return Global.el("div", { class: "request-card" }, [
    Global.el("div", { class: "request-info" }, [
      Global.el("strong", { text: invite.email }),
      Global.el("div", {
        class: "field-hint",
        text: `Asked for by ${invite.invited_by_email} - ${ROLE_TEXT[invite.role]} "${invite.trip_name || "a deleted trip"}" - ${asked}`,
      }),
    ]),
    Global.el("div", { class: "request-actions" }, buttons),
  ]);
}

async function load() {
  let invites;
  try {
    invites = await Global.withLoading(requestsEl, Global.fetchJSON("/api/admin/invites"));
  } catch (err) {
    requestsEl.replaceChildren(Global.el("p", { class: "field-hint", text: err.message }));
    return;
  }
  updateNavCount(invites.length);
  requestsEl.replaceChildren(
    ...(invites.length ? invites.map(requestCard) : [Global.el("p", { class: "field-hint", text: "Nothing is waiting." })])
  );
}

load();
