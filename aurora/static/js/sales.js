(function () {
  const $ = A.$, SK = { completed: "ok", voided: "bad", refunded: "bad", partially_refunded: "warn" };
  A.$("#from").value = A.daysFrom(-7); $("#to").value = A.today();
  async function load() {
    const p = new URLSearchParams({ q: $("#q").value, from: $("#from").value, to: $("#to").value, status: $("#st").value });
    let rows; try { rows = await A.get("/api/sales?" + p); } catch (e) { return A.fail(e); }
    $("#rows").innerHTML = rows.map((s) => `<tr class="click" data-id="${s.id}"><td><b>${A.esc(s.receipt_no)}</b></td><td class="muted nowrap">${A.dt(s.created_at)}</td><td>${A.esc(s.cashier_name)}</td><td>${A.esc(s.customer_name || "—")}</td><td class="muted">${A.esc((s.methods || "").replace(/,/g, ", "))}</td><td>${A.pill(s.status.replace("_", " "), SK[s.status])}</td><td class="num">${A.money(s.total_kobo)}</td></tr>`).join("") || `<tr><td colspan="7">${A.empty("receipt", "No sales found.")}</td></tr>`;
    A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => detail(+tr.dataset.id)));
  }
  ["q", "from", "to", "st"].forEach((i) => $("#" + i).addEventListener(i === "q" ? "input" : "change", A.debounce(load)));
  const csv = $("#csv"); if (csv) csv.addEventListener("click", () => A.download(`/api/reports/sales.csv?from=${$("#from").value}&to=${$("#to").value}`));
  async function detail(id) {
    const s = await A.get("/api/sales/" + id).catch(A.fail); if (!s) return;
    const canRefund = !["voided", "refunded"].includes(s.status);
    const r = await A.modal({ title: s.receipt_no, sub: `${A.dt(s.created_at)} · ${s.cashier_name}${s.customer_name ? " · " + s.customer_name : ""}`, size: "wide", html: `
      <div class="tbl-wrap"><table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Returned</th><th class="num">Total</th></tr></thead><tbody>${s.items.map((i) => `<tr><td>${A.esc(i.name)}</td><td class="num">${A.qty(i.qty)}</td><td class="num">${A.money(i.unit_price_kobo)}</td><td class="num">${i.returned_qty ? A.pill(A.qty(i.returned_qty), "warn") : ""}</td><td class="num">${A.money(i.total_kobo)}</td></tr>`).join("")}</tbody></table></div>
      <div class="grid g2" style="margin-top:12px"><div>${s.payments.map((p) => `<div class="row sp"><span class="muted">${A.esc(p.method)}</span><span>${A.money(p.amount_kobo)}</span></div>`).join("")}${s.change_kobo ? `<div class="row sp"><span class="muted">change given</span><span>${A.money(s.change_kobo)}</span></div>` : ""}
      ${s.refunds.map((f) => `<div class="row sp" style="color:var(--bad)"><span>Refund by ${A.esc(f.user_name)} (${A.esc(f.method)})${f.reason ? " — " + A.esc(f.reason) : ""}</span><span>−${A.money(f.total_kobo)}</span></div>`).join("")}</div>
      <div class="right"><div class="muted">VAT ${A.money(s.tax_kobo)}${s.discount_kobo ? " · discount " + A.money(s.discount_kobo) : ""}</div><div class="big-num">${A.money(s.total_kobo)}</div></div></div>`,
      actions: [{ label: "Close", value: null }, { label: "Print receipt", value: "print" }].concat(canRefund ? [{ label: "Refund / void", cls: "bad", value: "refund" }] : []) });
    if (r === "print") A.printReceipt(id); if (r === "refund") refund(s);
  }
  async function refund(s) {
    const left = s.items.filter((i) => i.qty - i.returned_qty > 0.0009);
    const untouched = s.items.every((i) => i.returned_qty === 0);
    const sameDay = s.created_at.slice(0, 10) === A.today();
    const res = await A.modal({ title: "Refund · " + s.receipt_no, size: "wide", sub: "Choose what the customer is returning. A manager PIN is needed unless you are a manager.", html: `
      <div class="tbl-wrap"><table><thead><tr><th>Item</th><th class="num">Can return</th><th class="num">Return qty</th><th>Back on shelf?</th></tr></thead><tbody>${left.map((i) => `<tr data-id="${i.id}"><td>${A.esc(i.name)}</td><td class="num">${A.qty(i.qty - i.returned_qty)}</td><td class="num"><input type="number" min="0" max="${i.qty - i.returned_qty}" step="any" value="0" style="width:90px" data-k="qty"></td><td><label class="chk"><input type="checkbox" data-k="restock" checked> Resellable</label></td></tr>`).join("")}</tbody></table></div>
      <div class="form" style="margin-top:12px"><label class="f">Money goes back by<select name="method"><option value="cash">Cash</option><option value="card">Card</option><option value="transfer">Transfer</option>${s.customer_id ? '<option value="account">Customer account / credit</option>' : ""}</select></label><label class="f">Reason<input name="reason" maxlength="200" placeholder="e.g. damaged, wrong item"></label></div>`,
      actions: [{ label: "Cancel", value: null }].concat(untouched ? [{ label: "Void whole sale", cls: "bad", run: (b) => submit(b, s, left, true) }] : []).concat([{ label: "Refund selected", cls: "pri", run: (b) => submit(b, s, left, false) }]) });
    if (res) { A.toast("Done. Refunded " + A.money(res.total_kobo) + "."); load(); }
  }
  async function submit(b, s, left, void_) {
    const d = A.form(b); if (!d.reason) { A.toast("Please give a reason.", "err"); return false; }
    const lines = A.$$("tr[data-id]", b).map((tr) => ({ sale_item_id: +tr.dataset.id, qty: parseFloat(A.$("[data-k=qty]", tr).value) || 0, restock: A.$("[data-k=restock]", tr).checked })).filter((l) => l.qty > 0);
    if (!void_ && !lines.length) { A.toast("Enter a quantity to return.", "err"); return false; }
    const r = await A.withPin((pin) => A.post(`/api/sales/${s.id}/refund`, { lines, method: d.method, reason: d.reason, void: void_, pin }));
    return r || false;
  }
  load();
})();
