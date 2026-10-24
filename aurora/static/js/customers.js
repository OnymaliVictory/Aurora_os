(function () {
  const canEdit = true, priv = A.cfg.price === "1";
  let rows = [];
  async function load() {
    try { rows = await A.get(`/api/customers?q=${encodeURIComponent(A.$("#q").value)}${A.$("#owing").checked ? "&owing=1" : ""}`); } catch (e) { return A.fail(e); }
    A.$("#rows").innerHTML = rows.map((c) => `<tr class="click" data-id="${c.id}"><td><b>${A.esc(c.name)}</b><div class="muted" style="font-size:12px">${c.orders_count} visits</div></td><td>${A.esc(c.phone || "—")}</td><td class="num">${c.loyalty_points}</td><td class="num">${A.money(c.total_spent_kobo)}</td>
      <td class="num">${c.balance_kobo > 0 ? A.pill(A.money(c.balance_kobo), "warn") : '<span class="faint">—</span>'}</td><td class="right"><button class="btn sm">${A.icon("eye", "sm")}</button></td></tr>`).join("") || `<tr><td colspan="6">${A.empty("users", "No customers yet.")}</td></tr>`;
    A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => view(+tr.dataset.id)));
  }
  A.$("#q").addEventListener("input", A.debounce(load)); A.$("#owing").addEventListener("change", load);
  async function view(id) {
    const c = await A.get("/api/customers/" + id).catch(A.fail); if (!c) return;
    const r = await A.modal({ title: c.name, sub: `${c.phone || "no phone"} · ${c.loyalty_points} points · credit limit ${A.money(c.credit_limit_kobo)}`, size: "wide", html: `
      <div class="grid g3" style="margin-bottom:14px"><div class="card stat"><div class="lbl">Total spent</div><div class="val">${A.money(c.total_spent_kobo)}</div></div><div class="card stat ${c.balance_kobo > 0 ? "warn" : ""}"><div class="lbl">Owes</div><div class="val">${A.money(c.balance_kobo)}</div></div><div class="card stat"><div class="lbl">Visits</div><div class="val">${c.orders_count}</div></div></div>
      <div class="grid g2"><div><h3 style="font-size:14px;margin-bottom:6px">Recent purchases</h3>${c.sales.map((s) => `<div class="list-row"><div class="grow">${A.esc(s.receipt_no)}<div class="muted" style="font-size:12px">${A.dt(s.created_at)}</div></div><b>${A.money(s.total_kobo)}</b></div>`).join("") || '<div class="muted">None yet.</div>'}</div>
      <div><h3 style="font-size:14px;margin-bottom:6px">Payments toward balance</h3>${c.payments.map((p) => `<div class="list-row"><div class="grow">${A.esc(p.method)}<div class="muted" style="font-size:12px">${A.dt(p.created_at)}</div></div><b>${A.money(p.amount_kobo)}</b></div>`).join("") || '<div class="muted">None yet.</div>'}</div></div>`,
      actions: [{ label: "Close", value: null }, { label: "Edit", value: "edit" }].concat(c.balance_kobo > 0 ? [{ label: "Record payment", cls: "pri", value: "pay" }] : []) });
    if (r === "edit") edit(c); if (r === "pay") pay(c);
  }
  async function pay(c) {
    const ok = await A.modal({ title: "Payment from " + c.name, sub: "Owes " + A.money(c.balance_kobo), size: "sm", html: `<div class="stack"><label class="f">Amount (${A.cfg.cur})<input name="amount" type="number" step="0.01" min="0" value="${A.naira(c.balance_kobo)}"></label><label class="f">Paid by<select name="method"><option value="cash">Cash</option><option value="transfer">Transfer</option><option value="card">Card</option></select></label></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Save payment", cls: "pri", run: async (b) => { await A.post(`/api/customers/${c.id}/pay`, A.form(b)); return true; } }] });
    if (ok) { A.toast("Payment recorded."); load(); }
  }
  async function edit(c) {
    const v = c || {};
    const r = await A.modal({ title: c ? "Edit customer" : "Add customer", html: `<div class="form"><label class="f">Name<input name="name" value="${A.esc(v.name || "")}"></label><label class="f">Phone<input name="phone" value="${A.esc(v.phone || "")}" inputmode="tel"></label><label class="f">Email<input name="email" value="${A.esc(v.email || "")}"></label>
      ${priv ? `<label class="f">Credit limit (${A.cfg.cur})<input name="credit_limit" type="number" min="0" step="0.01" value="${A.naira(v.credit_limit_kobo || 0)}"></label>` : ""}<label class="f full">Address<input name="address" value="${A.esc(v.address || "")}"></label><label class="f full">Notes<input name="notes" value="${A.esc(v.notes || "")}"></label></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Save", cls: "pri", run: async (b) => { const d = A.form(b); if (c) await A.put("/api/customers/" + c.id, d); else await A.post("/api/customers", d); return true; } }] });
    if (r) { A.toast("Saved."); load(); }
  }
  A.$("#add").addEventListener("click", () => edit(null));
  load();
})();
