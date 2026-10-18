// compare.html - a side-by-side scoring grid for one trip's candidate
// stays. Rows are the trip's stays (see models.Stay), columns are the
// user's own criteria (models.TripStayCriterion); each cell is a
// yes/partial/no/unknown verdict. Score is computed here from the
// verdicts and criterion weights - the server just stores the pieces.
//
// One read (GET /stay-comparison) fills everything. Structural changes
// (add / delete / reorder a criterion) reload; verdict clicks update
// optimistically so the grid doesn't jump.

const params = new URLSearchParams(window.location.search);
const tripId = Number(params.get("trip"));

const VERDICTS = ["unknown", "yes", "partial", "no"];
const VERDICT_LABEL = { unknown: "?", yes: "Yes", partial: "Part", no: "No" };
const VERDICT_SCORE = { yes: 1, partial: 0.5, no: 0, unknown: 0 };

let state = { home_currency: "USD", criteria: [], stays: [], verdictMap: {} };

function verdictKey(stayId, criterionId) {
  return `${stayId}:${criterionId}`;
}

function money(amount) {
  if (amount === null || amount === undefined) return "—";
  const rounded = Math.round(amount);
  return state.home_currency === "USD"
    ? `$${rounded.toLocaleString()}`
    : `${state.home_currency} ${rounded.toLocaleString()}`;
}

// --- scoring ---------------------------------------------------------------

function scoreFor(stay) {
  const totalWeight = state.criteria.reduce((sum, c) => sum + (c.weight || 1), 0);
  let earned = 0;
  let mustHaveFails = [];
  for (const c of state.criteria) {
    const v = state.verdictMap[verdictKey(stay.id, c.id)]?.verdict || "unknown";
    earned += (VERDICT_SCORE[v] ?? 0) * (c.weight || 1);
    if (c.must_have && v === "no") mustHaveFails.push(c.label);
  }
  return {
    pct: totalWeight ? Math.round((earned / totalWeight) * 100) : null,
    mustHaveFails,
  };
}

function perNight(stay) {
  if (stay.estimated_total == null || !stay.nights) return null;
  return stay.estimated_total / stay.nights;
}

// --- criteria editor ----------------------------------------------------

function renderCriteriaEditor() {
  const host = document.getElementById("criteria-editor");
  host.innerHTML = "";
  document.getElementById("criteria-count").textContent = state.criteria.length
    ? `${state.criteria.length}`
    : "";

  state.criteria.forEach((c, index) => {
    const row = Global.el("div", { class: "criterion-row" });

    const label = Global.el("input", { type: "text", value: c.label, class: "criterion-label-input" });
    label.addEventListener("change", () => patchCriterion(c.id, { label: label.value.trim() || c.label }));

    const weight = Global.el("input", { type: "number", min: "1", step: "1", value: c.weight, class: "criterion-weight-input" });
    weight.addEventListener("change", () => patchCriterion(c.id, { weight: Math.max(1, Number(weight.value) || 1) }));

    const must = Global.el("input", { type: "checkbox" });
    must.checked = c.must_have;
    must.addEventListener("change", () => patchCriterion(c.id, { must_have: must.checked }));

    const up = Global.el("button", { type: "button", class: "icon-btn", text: "↑", title: "Move up", onclick: () => moveCriterion(index, -1) });
    const down = Global.el("button", { type: "button", class: "icon-btn", text: "↓", title: "Move down", onclick: () => moveCriterion(index, 1) });
    up.disabled = index === 0;
    down.disabled = index === state.criteria.length - 1;

    const del = Global.el("button", {
      type: "button",
      class: "icon-btn danger",
      text: "✕",
      title: "Delete criterion",
      onclick: async () => {
        if (!confirm(`Delete criterion "${c.label}"? Its verdicts across all options go too.`)) return;
        await Global.fetchJSON(`${API_BASE}/stay-criteria/${c.id}`, { method: "DELETE" });
        load();
      },
    });

    row.append(
      label,
      Global.el("label", { class: "inline-field" }, [Global.el("span", { text: "×" }), weight]),
      Global.el("label", { class: "checkbox-label" }, [must, document.createTextNode("must-have")]),
      Global.el("div", { class: "criterion-row-actions" }, [up, down, del])
    );
    host.appendChild(row);
  });
  applyIcons(host);
}

async function patchCriterion(id, body) {
  try {
    await Global.fetchJSON(`${API_BASE}/stay-criteria/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await load();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

// Swap sort_order with the neighbor in the given direction - the same
// "just renumber the two that moved" approach as Manage Categories.
async function moveCriterion(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.criteria.length) return;
  const a = state.criteria[index];
  const b = state.criteria[target];
  try {
    await Promise.all([
      Global.fetchJSON(`${API_BASE}/stay-criteria/${a.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sort_order: b.sort_order }),
      }),
      Global.fetchJSON(`${API_BASE}/stay-criteria/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sort_order: a.sort_order }),
      }),
    ]);
    await load();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

function initAddCriterionForm() {
  const form = document.getElementById("add-criterion-form");
  const label = document.getElementById("criterion-label");
  const weight = document.getElementById("criterion-weight");
  const must = document.getElementById("criterion-must-have");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = label.value.trim();
    if (!text) return;
    try {
      await Global.fetchJSON(`${TRIPS_API}/${tripId}/stay-criteria`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: text,
          weight: Math.max(1, Number(weight.value) || 1),
          must_have: must.checked,
        }),
      });
      form.reset();
      weight.value = "1";
      label.focus();
      load();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

// --- the matrix ---------------------------------------------------------

function visibleStays() {
  const showArchived = document.getElementById("show-archived").checked;
  let rows = state.stays.filter((s) => showArchived || !s.archived);

  const sort = document.getElementById("sort-select").value;
  rows = rows.slice().sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name);
    if (sort === "cost") {
      const av = a.estimated_total ?? Infinity;
      const bv = b.estimated_total ?? Infinity;
      return av - bv;
    }
    // score, high to low; nulls last
    const as = scoreFor(a).pct ?? -1;
    const bs = scoreFor(b).pct ?? -1;
    return bs - as;
  });
  return rows;
}

function verdictButton(stay, criterion) {
  const current = state.verdictMap[verdictKey(stay.id, criterion.id)]?.verdict || "unknown";
  const btn = Global.el("button", {
    type: "button",
    class: `verdict-cell verdict-${current}`,
    text: VERDICT_LABEL[current],
    title: `${criterion.label}: ${current}`,
  });
  btn.addEventListener("click", async () => {
    const next = VERDICTS[(VERDICTS.indexOf(current) + 1) % VERDICTS.length];
    // optimistic
    state.verdictMap[verdictKey(stay.id, criterion.id)] = { verdict: next };
    renderMatrix();
    try {
      await Global.fetchJSON(`${API_BASE}/stays/${stay.id}/verdicts/${criterion.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict: next }),
      });
    } catch (err) {
      Global.showMessage(err.message, "error");
      load();
    }
  });
  return btn;
}

function renderMatrix() {
  const wrap = document.getElementById("matrix-wrap");
  const rows = visibleStays();
  document.getElementById("stay-count").textContent = rows.length ? `${rows.length}` : "";
  document.getElementById("matrix-empty").hidden = state.stays.length !== 0;
  wrap.innerHTML = "";
  if (!rows.length) return;

  const table = Global.el("table", { class: "matrix" });

  // header
  const headRow = Global.el("tr", {});
  headRow.appendChild(Global.el("th", { class: "sticky-col", text: "Option" }));
  headRow.appendChild(Global.el("th", { class: "num", text: "Est. total" }));
  headRow.appendChild(Global.el("th", { class: "num", text: "/ night" }));
  headRow.appendChild(Global.el("th", { class: "num", text: "Beds" }));
  headRow.appendChild(Global.el("th", { class: "num", text: "Sleeps" }));
  for (const c of state.criteria) {
    const th = Global.el("th", { class: "crit-col" }, [
      Global.el("span", { class: "crit-name", text: c.label }),
      Global.el("span", { class: "crit-meta", text: `×${c.weight}${c.must_have ? " · must" : ""}` }),
    ]);
    headRow.appendChild(th);
  }
  headRow.appendChild(Global.el("th", { class: "num", text: "Score" }));
  table.appendChild(headRow);

  for (const stay of rows) {
    const { pct, mustHaveFails } = scoreFor(stay);
    const tr = Global.el("tr", { class: mustHaveFails.length ? "must-fail" : "" });

    const nameCell = Global.el("td", { class: "sticky-col" });
    const nameNode = stay.url
      ? Global.el("a", { href: stay.url, target: "_blank", rel: "noopener noreferrer", text: stay.name })
      : Global.el("span", { text: stay.name });
    nameCell.appendChild(nameNode);
    const tags = Global.el("div", { class: "matrix-tags" });
    if (stay.booked) tags.appendChild(Global.el("span", { class: "item-badge item-badge-booked", text: "Booked" }));
    if (stay.needs_review) tags.appendChild(Global.el("span", { class: "item-badge item-badge-review", text: "Review" }));
    if (stay.archived) tags.appendChild(Global.el("span", { class: "item-badge item-badge-archived", text: "Archived" }));
    if (tags.children.length) nameCell.appendChild(tags);
    tr.appendChild(nameCell);

    const totalCell = Global.el("td", { class: "num" }, [
      Global.el("span", { text: money(stay.estimated_total) }),
    ]);
    if (stay.estimated_total != null && stay.cost == null) {
      totalCell.appendChild(Global.el("span", { class: "est-flag", text: " est" }));
    }
    const useBtn = Global.el("button", {
      type: "button",
      class: "link-btn",
      text: "use as cost",
      title: "Copy this estimate into the stay's confirmed cost",
      onclick: async () => {
        try {
          await Global.fetchJSON(`${API_BASE}/stays/${stay.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cost: stay.estimated_total }),
          });
          load();
        } catch (err) {
          Global.showMessage(err.message, "error");
        }
      },
    });
    if (stay.estimated_total != null && stay.cost == null) totalCell.appendChild(useBtn);
    tr.appendChild(totalCell);

    const pn = perNight(stay);
    tr.appendChild(Global.el("td", { class: "num", text: pn == null ? "—" : money(pn) }));
    tr.appendChild(Global.el("td", { class: "num", text: stay.bedrooms ?? "—" }));
    tr.appendChild(Global.el("td", { class: "num", text: stay.sleeps ?? "—" }));

    for (const c of state.criteria) {
      const td = Global.el("td", { class: "verdict-td" });
      td.appendChild(verdictButton(stay, c));
      tr.appendChild(td);
    }

    const scoreCell = Global.el("td", { class: "num score-cell" });
    if (pct == null) {
      scoreCell.appendChild(Global.el("span", { class: "score-pct muted", text: "—" }));
    } else {
      scoreCell.appendChild(Global.el("span", { class: "score-pct", text: `${pct}%` }));
      const bar = Global.el("div", { class: "score-bar" }, [Global.el("div", { class: "score-bar-fill" })]);
      bar.querySelector(".score-bar-fill").style.width = `${pct}%`;
      scoreCell.appendChild(bar);
    }
    if (mustHaveFails.length) {
      scoreCell.appendChild(Global.el("span", { class: "must-fail-tag", text: `✗ ${mustHaveFails.join(", ")}` }));
    }
    tr.appendChild(scoreCell);

    table.appendChild(tr);
  }

  wrap.appendChild(table);
}

// --- load -------------------------------------------------------------

async function load() {
  const data = await Global.withLoading(document.getElementById("matrix-wrap"), Global.fetchJSON(`${TRIPS_API}/${tripId}/stay-comparison`));
  state.home_currency = data.home_currency || "USD";
  state.criteria = data.criteria;
  state.stays = data.stays;
  state.verdictMap = {};
  for (const v of data.verdicts) {
    state.verdictMap[verdictKey(v.stay_id, v.criterion_id)] = { verdict: v.verdict, note: v.note };
  }
  renderCriteriaEditor();
  renderMatrix();
}

async function init() {
  if (!tripId) {
    Global.showMessage("No trip specified.", "error");
    return;
  }
  try {
    const trip = await Global.fetchJSON(`${TRIPS_API}/${tripId}`);
    document.getElementById("page-title").textContent = `Compare stays — ${trip.location}`;
    document.getElementById("back-to-trip").href = `trip.html?id=${tripId}`;
  } catch (err) {
    Global.showMessage(err.message, "error");
    return;
  }

  initAddCriterionForm();
  document.getElementById("sort-select").addEventListener("change", renderMatrix);
  document.getElementById("show-archived").addEventListener("change", renderMatrix);

  try {
    await load();
  } catch (err) {
    Global.showMessage(err.message, "error");
  }
}

init();
