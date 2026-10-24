(function () {
  const $ = A.$, SK = { draft: "", ordered: "info", partial: "warn", received: "ok", cancelled: "bad" };
  async function load() {
    let rows; try { rows = await A.get("/api/purchases"); } catch (e) { return A.fail(e); }
    $("#rows").innerHTML = rows.map((o) => `<tr class="click" data-id="${o.id}"><td><b>${A.esc(o.po_no)}</b></td><td>${A.esc(o.supplier_name || "—")}</td><td>${A.pill(o.status, SK[o.status])}</td><td class="muted">${A.date(o.created_at)}</td><td class="num">${o.lines}</td><td class="num">${A.money(o.total_kobo)}</td><td class="num">${o.paid_kobo >= o.total_kobo && o.total_kobo ? A.pill("Paid", "ok") : A.money(o.paid_kobo)}</td></tr>`).join("") || `<tr><td colspan="7">${A.empty("truck", "No purchase orders yet.")}</td></tr>`;
    A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => detail(+tr.dataset.id)));
  }
  // ----- create -----
  async function create(prefill) {
    const [sups, prods] = await Promise.all([A.get("/api/suppliers"), A.get("/api/products?limit=500&active_only=1")]);
    const items = prefill || [];
    const r = await A.modal({ title: "New purchase order", size: "wide", html: `<div class="form"><label class="f">Supplier<select name="supplier_id"><option value="">— choose —</option>${sups.map((s) => `<option value="${s.id}">${A.esc(s.name)}</option>`).join("")}</select></label><label class="f">Expected on<input name="expected_on" type="date"></label></div>
      <div class="row" style="margin:14px 0 6px"><select id="pp" style="flex:1"><option value="">+ Add a product…</option>${prods.map((p) => `<option value="${p.id}">${A.esc(p.name)}</option>`).join("")}</select></div>
      <div class="tbl-wrap" style="max-height:300px"><table><thead><tr><th>Product</th><th class="num">Qty</th><th class="num">Cost each (${A.cfg.cur})</th><th class="num">Line total</th><th></th></tr></thead><tbody id="pl"></tbody></table></div>
      <div class="row sp" style="margin-top:10px"><label class="f" style="flex:1">Note<input name="note" maxlength="200"></label><div class="big-num" id="gt">${A.money(0)}</div></div>`,
      onOpen: (b) => {
        const draw = () => { $("#pl", b).innerHTML = items.map((it, i) => `<tr><td>${A.esc(it.name)}</td><td class="num"><input data-i="${i}" data-k="qty" type="number" min="0" step="0.001" value="${it.qty}" style="width:90px"></td><td class="num"><input data-i="${i}" data-k="cost" type="number" min="0" step="0.01" value="${A.naira(it.cost_kobo || 0)}" style="width:110px"></td><td class="num" id="lt${i}">${A.money(Math.round(it.qty * (it.cost_kobo || 0)))}</td><td><button class="btn sm bad" data-rm="${i}">${A.icon("x", "sm")}</button></td></tr>`).join("") || `<tr><td colspan="5" class="muted">Pick products above.</td></tr>`;
          tot(); A.$$("[data-i]", b).forEach((inp) => inp.addEventListener("input", () => { const it = items[+inp.dataset.i]; if (inp.dataset.k === "qty") it.qty = parseFloat(inp.value) || 0; else it.cost_kobo = A.toKobo(inp.value); $("#lt" + inp.dataset.i, b).textContent = A.money(Math.round(it.qty * it.cost_kobo)); tot(); }));
          A.$$("[data-rm]", b).forEach((x) => x.addEventListener("click", () => { items.splice(+x.dataset.rm, 1); draw(); })); };
        const tot = () => ($("#gt", b).textContent = A.money(items.reduce((a, it) => a + Math.round(it.qty * (it.cost_kobo || 0)), 0)));
        $("#pp", b).addEventListener("change", (e) => { const p = prods.find((x) => x.id == e.target.value); if (p && !items.find((i) => i.product_id === p.id)) items.push({ product_id: p.id, name: p.name, qty: 1, cost_kobo: p.cost_kobo || 0 }); e.target.value = ""; draw(); });
        draw();
      },
      actions: [{ label: "Cancel", value: null }, { label: "Save draft", run: (b) => save(b, items, "draft") }, { label: "Place order", cls: "pri", run: (b) => save(b, items, "ordered") }] });
    if (r) { A.toast("Order saved."); load(); }
  }
  async function save(b, items, status) {
    const d = A.form(b); d.status = status; d.items = items.filter((i) => i.qty > 0).map((i) => ({ product_id: i.product_id, qty: i.qty, cost: A.naira(i.cost_kobo || 0) }));
    await A.post("/api/purchases", d); return true;
  }
  $("#add").addEventListener("click", () => create());
  $("#sugg").addEventListener("click", async () => {
    const s = await A.get("/api/purchases/suggest");
    if (!s.length) return A.toast("Nothing is running low — great!");
    create(s.map((p) => ({ product_id: p.id, name: p.name, qty: Math.ceil(p.suggest), cost_kobo: p.cost_kobo })));
  });
  // ----- detail -----
  async function detail(id) {
    const o = await A.get("/api/purchases/" + id).catch(A.fail); if (!o) return;
    const open = ["ordered", "partial"].includes(o.status), owe = o.total_kobo - o.paid_kobo;
    const act = [{ label: "Close", value: null }];
    if (o.status === "draft") act.push({ label: "Cancel order", cls: "bad", value: "cancelled" }, { label: "Place order", cls: "pri", value: "ordered" });
    if (open) act.push({ label: "Cancel order", cls: "bad", value: "cancelled" }, { label: "Receive delivery", cls: "pri", value: "receive" });
    if (["partial", "received"].includes(o.status) && owe > 0) act.push({ label: "Pay supplier", value: "pay" });
    const r = await A.modal({ title: o.po_no, sub: `${o.supplier_name || "No supplier"} · ${o.status}`, size: "wide", html: `<div class="tbl-wrap"><table><thead><tr><th>Product</th><th class="num">Ordered</th><th class="num">Received</th><th class="num">Cost</th></tr></thead><tbody>${o.items.map((i) => `<tr><td>${A.esc(i.name)}</td><td class="num">${A.qty(i.qty_ordered)}</td><td class="num">${A.qty(i.qty_received)}</td><td class="num">${A.money(i.cost_kobo)}</td></tr>`).join("")}</tbody></table></div><div class="row sp" style="margin-top:10px"><span class="muted">${A.esc(o.note || "")}</span><span>Total <b>${A.money(o.total_kobo)}</b> · Paid <b>${A.money(o.paid_kobo)}</b></span></div>`, actions: act });
    if (r === "ordered" || r === "cancelled") { try { await A.post(`/api/purchases/${id}/status`, { status: r }); load(); } catch (e) { A.fail(e); } }
    if (r === "receive") receive(o);
    if (r === "pay") { const a = await A.modal({ title: "Pay supplier", sub: "You owe " + A.money(owe), size: "sm", html: `<label class="f">Amount (${A.cfg.cur})<input id="pa" type="number" step="0.01" value="${A.naira(owe)}"></label>`, actions: [{ label: "Cancel", value: null }, { label: "Record payment", cls: "pri", run: async (b) => { await A.post(`/api/purchases/${id}/pay`, { amount: A.$("#pa", b).value }); return true; } }] }); if (a) { A.toast("Payment recorded."); load(); } }
  }
  async function receive(o) {
    const todo = o.items.filter((i) => i.qty_received < i.qty_ordered);
    const r = await A.modal({ title: "Receive delivery · " + o.po_no, sub: "Enter what actually arrived. Each line becomes a batch with its own expiry date.", size: "wide", html: `<div class="tbl-wrap"><table><thead><tr><th>Product</th><th class="num">Still due</th><th class="num">Arrived</th><th>Expiry</th><th class="num">Cost each</th></tr></thead><tbody>${todo.map((i) => `<tr data-id="${i.id}"><td>${A.esc(i.name)}</td><td class="num">${A.qty(i.qty_ordered - i.qty_received)}</td><td class="num"><input data-k="qty" type="number" min="0" step="0.001" value="${i.qty_ordered - i.qty_received}" style="width:90px"></td><td><input data-k="expiry_date" type="date"></td><td class="num"><input data-k="cost" type="number" step="0.01" value="${A.naira(i.cost_kobo)}" style="width:100px"></td></tr>`).join("")}</tbody></table></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Add to stock", cls: "pri", run: async (b) => { const lines = A.$$("tr[data-id]", b).map((tr) => ({ item_id: +tr.dataset.id, qty: A.$("[data-k=qty]", tr).value, expiry_date: A.$("[data-k=expiry_date]", tr).value, cost: A.$("[data-k=cost]", tr).value })); await A.post(`/api/purchases/${o.id}/receive`, { lines }); return true; } }] });
    if (r) { A.toast("Stock updated."); load(); }
  }
  load();
})();
