(function () {
  const $ = A.$, showCost = A.cfg.cost === "1";
  let cats = [], sups = [], filter = new URLSearchParams(location.search).get("filter") || "";
  A.$$("#flt button").forEach((b) => { b.classList.toggle("on", b.dataset.f === filter); b.addEventListener("click", () => { filter = b.dataset.f; A.$$("#flt button").forEach((x) => x.classList.toggle("on", x === b)); load(); }); });

  async function boot() {
    [cats, sups] = await Promise.all([A.get("/api/categories"), A.get("/api/suppliers").catch(() => [])]);
    $("#cat").innerHTML = '<option value="">All categories</option>' + cats.map((c) => `<option value="${c.id}">${A.esc(c.emoji)} ${A.esc(c.name)} (${c.n})</option>`).join("");
    load();
  }
  async function load() {
    const p = new URLSearchParams({ q: $("#q").value, category: $("#cat").value, filter, limit: 500 });
    let rows; try { rows = await A.get("/api/products?" + p); } catch (e) { return A.fail(e); }
    const tb = $("#rows"), today = A.today(), soon = A.daysFrom(30);
    if (!rows.length) { tb.innerHTML = `<tr><td colspan="8">${A.empty("package", filter || $("#q").value ? "No products match." : "No products yet. Add one, import a CSV, or load the sample products in Settings.")}</td></tr>`; return; }
    tb.innerHTML = rows.map((r) => {
      const out = r.track_stock && r.qty <= 0, low = r.track_stock && !out && r.qty <= r.min_stock;
      const ex = r.next_expiry ? (r.next_expiry < today ? A.pill("Expired " + A.date(r.next_expiry), "bad") : r.next_expiry <= soon ? A.pill(A.date(r.next_expiry), "warn") : `<span class="muted">${A.date(r.next_expiry)}</span>`) : '<span class="faint">—</span>';
      return `<tr class="click" data-id="${r.id}"><td><b>${A.esc(r.name)}</b>${r.status === "inactive" ? " " + A.pill("hidden") : ""}<div class="muted" style="font-size:12px">${A.esc(r.barcode || "no barcode")}${r.brand ? " · " + A.esc(r.brand) : ""}</div></td>
      <td>${r.category_name ? `<span class="dot" style="background:${A.esc(r.category_color)}"></span>${A.esc(r.category_name)}` : '<span class="faint">—</span>'}</td>
      <td class="num">${A.money(r.price_kobo)}</td>${showCost ? `<td class="num muted">${A.money(r.cost_kobo)}</td>` : ""}
      <td class="num">${r.track_stock ? `${A.qty(r.qty)} <span class="muted">${A.esc(r.unit)}</span> ${out ? A.pill("Out", "bad") : low ? A.pill("Low", "warn") : ""}` : '<span class="faint">not tracked</span>'}</td>
      <td>${ex}</td><td class="right nowrap"><button class="btn sm" data-a="stock">${A.icon("package-plus", "sm")} Stock</button> <button class="btn sm" data-a="edit">${A.icon("pencil", "sm")}</button></td></tr>`;
    }).join("");
    A.$$("tr[data-id]", tb).forEach((tr) => tr.addEventListener("click", (e) => { const a = e.target.closest("[data-a]"); openProduct(+tr.dataset.id, a && a.dataset.a === "stock" ? "stock" : "edit"); }));
  }
  $("#q").addEventListener("input", A.debounce(load)); $("#cat").addEventListener("change", load);

  const catOpts = (sel) => '<option value="">— none —</option>' + cats.map((c) => `<option value="${c.id}" ${c.id == sel ? "selected" : ""}>${A.esc(c.emoji)} ${A.esc(c.name)}</option>`).join("");
  const supOpts = (sel) => '<option value="">— none —</option>' + sups.map((c) => `<option value="${c.id}" ${c.id == sel ? "selected" : ""}>${A.esc(c.name)}</option>`).join("");

  async function openProduct(id, tab) {
    const p = id ? await A.get("/api/products/" + id).catch(A.fail) : null;
    if (id && !p) return;
    if (p && tab === "stock") return stockModal(p);
    const v = p || { name: "", barcode: "", sku: "", brand: "", unit: "pcs", is_weighed: 0, price_kobo: 0, cost_kobo: 0, tax_exempt: 0, min_stock: 5, track_stock: 1, status: "active" };
    const r = await A.modal({ title: p ? "Edit product" : "Add product", size: "wide", html: `<div class="form">
      <label class="f full">Name<input name="name" value="${A.esc(v.name)}"></label>
      <label class="f">Barcode<input name="barcode" value="${A.esc(v.barcode || "")}" placeholder="Scan or type"></label>
      <label class="f">SKU / code<input name="sku" value="${A.esc(v.sku || "")}"></label>
      <label class="f">Category<select name="category_id">${catOpts(v.category_id)}</select></label>
      <label class="f">Supplier<select name="supplier_id">${supOpts(v.supplier_id)}</select></label>
      <label class="f">Brand<input name="brand" value="${A.esc(v.brand || "")}"></label>
      <label class="f">Unit<input name="unit" value="${A.esc(v.unit)}" placeholder="pcs, kg, pack"></label>
      <label class="f">Selling price (${A.cfg.cur})<input name="price" type="number" step="0.01" min="0" value="${A.naira(v.price_kobo)}"></label>
      ${showCost ? `<label class="f">Cost price (${A.cfg.cur})<input name="cost" type="number" step="0.01" min="0" value="${A.naira(v.cost_kobo || 0)}"></label>` : ""}
      <label class="f">Reorder level (alert when stock reaches this)<input name="min_stock" type="number" step="0.001" min="0" value="${v.min_stock}"></label>
      ${p ? "" : `<label class="f">Opening stock<input name="opening_qty" type="number" step="0.001" min="0" value="0"></label><label class="f">Expiry date of that stock<input name="expiry_date" type="date"></label>`}
      <label class="chk"><input type="checkbox" name="is_weighed" ${v.is_weighed ? "checked" : ""}> Sold by weight (kg) at the till</label>
      <label class="chk"><input type="checkbox" name="tax_exempt" ${v.tax_exempt ? "checked" : ""}> VAT-exempt (e.g. basic foods)</label>
      <label class="chk"><input type="checkbox" name="track_stock" ${v.track_stock ? "checked" : ""}> Track stock</label>
      <label class="chk"><input type="checkbox" name="active" ${v.status === "active" ? "checked" : ""}> Visible at the till</label></div>`,
      actions: [{ label: "Cancel", value: null }].concat(p ? [{ label: "Delete", cls: "bad", value: "del" }] : []).concat([{ label: "Save", cls: "pri", run: async (b) => {
        const d = A.form(b); d.status = d.active ? "active" : "inactive";
        if (p) await A.put("/api/products/" + id, d); else await A.post("/api/products", d);
        return true; } }]) });
    if (r === "del") { if (await A.confirm("Delete " + p.name + "?", "It disappears from the till. Past sales keep their history.", "Delete", true)) { try { await A.del("/api/products/" + id); A.toast("Product deleted."); load(); } catch (e) { A.fail(e); } } return; }
    if (r) { A.toast("Saved."); boot(); }
  }
  async function stockModal(p) {
    const lots = p.lots.map((l) => `<tr><td>${A.qty(l.qty)}</td><td>${l.expiry_date ? A.date(l.expiry_date) : "—"}</td><td class="muted">${A.dt(l.received_at)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">No stock on hand.</td></tr>`;
    const moves = p.moves.slice(0, 12).map((m) => `<tr><td class="muted">${A.dt(m.created_at)}</td><td>${A.esc(m.reason)}</td><td class="num" style="color:${m.qty_change < 0 ? "var(--bad)" : "var(--ok)"}">${m.qty_change > 0 ? "+" : ""}${A.qty(m.qty_change)}</td><td class="num">${A.qty(m.qty_after)}</td></tr>`).join("");
    const r = await A.modal({ title: p.name, sub: `In stock: ${A.qty(p.qty)} ${p.unit}`, size: "wide", html: `
      <div class="grid g2"><div class="stack">
      <div class="seg" id="act"><button type="button" data-a="receive" class="on">Receive</button><button type="button" data-a="damage">Damaged</button><button type="button" data-a="expired">Expired</button><button type="button" data-a="correct">Recount</button></div>
      <label class="f"><span id="qlbl">Quantity received</span><input name="qty" type="number" step="0.001" min="0"></label>
      <label class="f" id="exw">Expiry date<input name="expiry_date" type="date"></label>
      ${showCost ? `<label class="f" id="cow">Cost each (${A.cfg.cur})<input name="cost" type="number" step="0.01" value="${A.naira(p.cost_kobo || 0)}"></label>` : ""}
      <label class="f">Note (optional)<input name="note" maxlength="160"></label></div>
      <div><h3 style="font-size:14px;margin-bottom:6px">Batches (sold oldest-expiry first)</h3><div class="tbl-wrap" style="max-height:130px"><table><thead><tr><th>Qty</th><th>Expires</th><th>Received</th></tr></thead><tbody>${lots}</tbody></table></div>
      <h3 style="font-size:14px;margin:14px 0 6px">Recent movements</h3><div class="tbl-wrap" style="max-height:170px"><table><thead><tr><th>When</th><th>Why</th><th class="num">Change</th><th class="num">After</th></tr></thead><tbody>${moves}</tbody></table></div></div></div>`,
      onOpen: (b) => { let act = "receive"; const sync = () => { const L = { receive: "Quantity received", damage: "Quantity damaged", expired: "Quantity expired", correct: "Counted quantity on the shelf" }; $("#qlbl", b).textContent = L[act]; $("#exw", b).classList.toggle("hide", act !== "receive"); const c = $("#cow", b); if (c) c.classList.toggle("hide", act !== "receive"); };
        A.$$("#act button", b).forEach((x) => x.addEventListener("click", () => { act = x.dataset.a; A.$$("#act button", b).forEach((y) => y.classList.toggle("on", y === x)); b._act = act; sync(); })); b._act = act; },
      actions: [{ label: "Close", value: null }, { label: "Save", cls: "pri", run: async (b) => { const d = A.form(b); d.action = b._act; const r = await A.post("/api/products/" + p.id + "/stock", d); A.toast(r.message); return true; } }] });
    if (r) load();
  }
  $("#add-btn").addEventListener("click", () => openProduct(0));

  // categories
  $("#cats-btn").addEventListener("click", async () => {
    const draw = () => cats.map((c) => `<div class="list-row"><span style="font-size:20px">${A.esc(c.emoji)}</span><span class="dot" style="background:${A.esc(c.color)}"></span><div class="grow">${A.esc(c.name)} <span class="muted">(${c.n})</span></div><button class="btn sm" data-e="${c.id}">${A.icon("pencil", "sm")}</button><button class="btn sm bad" data-d="${c.id}">${A.icon("trash-2", "sm")}</button></div>`).join("") || A.empty("tags", "No categories yet.");
    await A.modal({ title: "Categories", size: "", html: `<div id="cl">${draw()}</div><div class="row" style="margin-top:12px"><input id="ce" style="width:70px" placeholder="🛒" maxlength="4"><input id="cn" placeholder="New category name" style="flex:1"><input id="cc" type="color" value="#34d399" style="width:50px;padding:2px"><button class="btn pri" id="ca">Add</button></div>`,
      onOpen: (b) => {
        const bind = () => { A.$$("[data-d]", b).forEach((x) => x.addEventListener("click", async () => { if (await A.confirm("Delete this category?", "Products in it become uncategorised.", "Delete", true)) { await A.del("/api/categories/" + x.dataset.d); cats = cats.filter((c) => c.id != x.dataset.d); $("#cl", b).innerHTML = draw(); bind(); } }));
          A.$$("[data-e]", b).forEach((x) => x.addEventListener("click", async () => { const c = cats.find((k) => k.id == x.dataset.e); const n = window.prompt("Rename category", c.name); if (n && n.trim()) { await A.put("/api/categories/" + c.id, { name: n, color: c.color, emoji: c.emoji }).catch(A.fail); cats = await A.get("/api/categories"); $("#cl", b).innerHTML = draw(); bind(); } })); };
        bind();
        $("#ca", b).addEventListener("click", async () => { try { await A.post("/api/categories", { name: $("#cn", b).value, emoji: $("#ce", b).value || "🛒", color: $("#cc", b).value }); cats = await A.get("/api/categories"); $("#cl", b).innerHTML = draw(); $("#cn", b).value = ""; bind(); } catch (e) { A.fail(e); } });
      } });
    boot();
  });

  // CSV
  $("#exp-btn").addEventListener("click", () => A.download("/api/products/export.csv"));
  $("#imp-btn").addEventListener("click", async () => {
    const go = await A.modal({ title: "Import products from a spreadsheet", size: "", html: `<p class="muted" style="margin-top:0">Save your spreadsheet as <b>CSV</b>. Columns: <code>name, barcode, sku, category, brand, unit, cost, price, tax_exempt, min_stock, qty, expiry_date</code>. Only <b>name</b> and <b>price</b> are required. Products with a matching barcode or SKU are updated instead of duplicated.</p><button class="btn" id="tpl">${A.icon("download")} Download a blank template</button>`,
      actions: [{ label: "Cancel", value: null }, { label: "Choose CSV file…", cls: "pri", value: true }], onOpen: (b) => $("#tpl", b).addEventListener("click", () => { const t = "name,barcode,sku,category,brand,unit,cost,price,tax_exempt,min_stock,qty,expiry_date\nExample Milk 1L,6001234567890,,Dairy,Peak,pcs,900,1200,0,10,24,2027-01-31\n"; const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([t], { type: "text/csv" })); a.download = "aurora-products-template.csv"; a.click(); }) });
    if (go) $("#file").click();
  });
  $("#file").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (f.size > 6 * 1024 * 1024) return A.toast("That file is too big.", "err");
    try { const r = await A.post("/api/products/import", { csv: await f.text() });
      await A.modal({ title: "Import finished", html: `<p><b>${r.added}</b> added · <b>${r.updated}</b> updated</p>${r.problems.length ? `<div class="err-box" style="max-height:200px;overflow:auto">${r.problems.map(A.esc).join("<br>")}</div>` : ""}` }); boot(); } catch (x) { A.fail(x); }
    e.target.value = "";
  });
  boot();
})();
