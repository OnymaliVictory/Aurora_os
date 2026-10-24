(function () {
  const S = { cart: [], customer: null, cartDiscount: null, quote: null, pin: null, cat: "", products: [], held: [], shift: null, heldId: null };
  const $ = A.$;
  const tb2 = $("#theme-btn2"); if (tb2) tb2.addEventListener("click", () => $("#theme-btn").click());

  // ------------- product grid -------------
  async function loadCats() {
    const cats = await A.get("/api/categories");
    $("#cats").innerHTML = `<button class="cat on" data-c="">All</button>` + cats.map((c) => `<button class="cat" data-c="${c.id}">${A.esc(c.emoji)} ${A.esc(c.name)}</button>`).join("");
    A.$$(".cat").forEach((b) => b.addEventListener("click", () => { S.cat = b.dataset.c; A.$$(".cat").forEach((x) => x.classList.toggle("on", x === b)); loadProducts(); }));
  }
  async function loadProducts() {
    const q = $("#q").value.trim();
    try { S.products = await A.get(`/api/pos/products?q=${encodeURIComponent(q)}&category=${S.cat}`); } catch (e) { return A.fail(e); }
    renderTiles();
  }
  function renderTiles() {
    const t = $("#tiles");
    if (!S.products.length) { t.innerHTML = A.empty("search", "No products found."); return; }
    t.innerHTML = S.products.map((p) => {
      const out = p.track_stock && p.qty <= 0, low = p.track_stock && p.qty > 0 && p.qty <= p.min_stock;
      return `<div class="tile ${out ? "out" : ""}" role="button" tabindex="0" data-id="${p.id}"><span class="em">${A.esc(p.category_emoji || "🛒")}</span><b>${A.esc(p.name)}</b>
        <span class="pr">${A.money(p.price_kobo)}${p.is_weighed ? '<small class="muted">/kg</small>' : ""}</span>
        <span class="st">${p.track_stock ? (out ? "Out of stock" : A.qty(p.qty) + " " + A.esc(p.unit)) : "Service"}</span>${low ? '<span class="pill warn tag">Low</span>' : ""}</div>`;
    }).join("");
    A.$$(".tile", t).forEach((b) => { const go = () => addProduct(S.products.find((p) => p.id == b.dataset.id)); b.addEventListener("click", go); b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }); });
  }
  const search = A.debounce(loadProducts, 220);
  $("#q").addEventListener("input", search);
  $("#q").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const v = e.target.value.trim(); if (!v) return;
    e.preventDefault();
    try { const p = await A.get("/api/pos/barcode/" + encodeURIComponent(v)); e.target.value = ""; addProduct(p); loadProducts(); }
    catch (x) { if (S.products.length === 1) { addProduct(S.products[0]); e.target.value = ""; loadProducts(); } else A.toast("No exact match — pick from the list.", "err"); }
  });

  // ------------- cart -------------
  async function addProduct(p) {
    if (!p) return;
    if (p.track_stock && p.qty <= 0) { A.toast(p.name + " is out of stock.", "err"); return; }
    let qty = 1;
    if (p.is_weighed) {
      const w = await A.modal({ title: p.name, sub: `Weigh it, then enter the weight in kg · ${A.money(p.price_kobo)}/kg`, size: "sm",
        html: `<label class="f">Weight (kg)<input id="w" type="number" step="0.001" min="0.001" inputmode="decimal"></label>`,
        actions: [{ label: "Cancel", value: null }, { label: "Add", cls: "pri", run: (b) => { const v = parseFloat($("#w", b).value); if (!(v > 0)) { A.toast("Enter the weight.", "err"); return false; } return v; } }] });
      if (!w) return; qty = w;
    }
    const ex = S.cart.find((l) => l.product_id === p.id && !p.is_weighed);
    if (ex) ex.qty += 1; else S.cart.push({ product_id: p.id, name: p.name, unit: p.unit, is_weighed: p.is_weighed, qty, price_kobo: null, discount_pct: 0 });
    refresh();
  }
  const payload = () => ({
    items: S.cart.map((l) => ({ product_id: l.product_id, qty: l.qty, price_kobo: l.price_kobo, discount_pct: l.discount_pct || 0 })),
    cart_discount: S.cartDiscount, customer_id: S.customer ? S.customer.id : null, pin: S.pin,
  });
  let seq = 0, lastGood = null, rolling = false;
  async function refresh() {
    const my = ++seq;
    renderLines();
    if (!S.cart.length) { S.quote = null; S.pin = null; lastGood = null; renderTotals(); return; }
    try {
      let r = await A.post("/api/pos/quote", payload());
      if (r.need_pin) {
        const pin = await A.pin(r.reason);
        if (!pin) return rollback();
        S.pin = pin; r = await A.post("/api/pos/quote", payload());
        if (r.need_pin) throw new Error("That PIN can't approve this.");
      }
      if (my !== seq) return;
      S.quote = r; lastGood = { cart: JSON.stringify(S.cart), disc: S.cartDiscount };
    } catch (e) { A.fail(e); S.pin = null; return rollback(); }
    renderLines(); renderTotals();
  }
  // If the server refused a change (no stock, bad PIN…), go back to the last basket that worked.
  function rollback() {
    if (rolling) return;
    if (lastGood) { S.cart = JSON.parse(lastGood.cart); S.cartDiscount = lastGood.disc; } else { S.cart = []; S.cartDiscount = null; }
    rolling = true; refresh().finally(() => { rolling = false; });
  }

  function renderLines() {
    const box = $("#lines");
    if (!S.cart.length) { box.innerHTML = A.empty("shopping-basket", "Basket is empty. Tap a product or scan a barcode."); return; }
    box.innerHTML = S.cart.map((l, i) => {
      const q = S.quote && S.quote.lines[i];
      return `<div class="line" data-i="${i}"><div><div class="nm">${A.esc(l.name)}</div>
        <div class="muted" style="font-size:12px">${A.money(q ? q.unit_price_kobo : 0)} ${l.is_weighed ? "/kg" : "each"}${q && q.discount_kobo ? ` · <span style="color:var(--ok)">−${A.money(q.discount_kobo)}</span>` : ""}</div>
        <div class="qty"><button data-a="minus" aria-label="Less">${A.icon("minus", "sm")}</button>
        <input data-a="qty" value="${A.qty(l.qty)}" inputmode="decimal" aria-label="Quantity"><button data-a="plus" aria-label="More">${A.icon("plus", "sm")}</button>
        <button data-a="edit" title="Discount / price">${A.icon("pencil", "sm")}</button></div></div>
        <div class="right"><b>${q ? A.money(q.total_kobo) : "…"}</b><div><button class="btn sm ghost" data-a="rm" aria-label="Remove">${A.icon("x", "sm")}</button></div></div></div>`;
    }).join("");
    A.$$(".line", box).forEach((row) => {
      const i = +row.dataset.i, l = S.cart[i];
      row.addEventListener("click", async (e) => {
        const a = e.target.closest("[data-a]"); if (!a) return;
        const act = a.dataset.a;
        if (act === "plus") l.qty = l.is_weighed ? Math.round((l.qty + 0.1) * 1000) / 1000 : l.qty + 1;
        else if (act === "minus") { l.qty = l.is_weighed ? Math.round((l.qty - 0.1) * 1000) / 1000 : l.qty - 1; if (l.qty <= 0) S.cart.splice(i, 1); }
        else if (act === "rm") S.cart.splice(i, 1);
        else if (act === "edit") return editLine(i);
        else return;
        refresh();
      });
      const inp = $("[data-a=qty]", row);
      inp.addEventListener("change", () => { const v = parseFloat(inp.value); if (v > 0) { l.qty = l.is_weighed ? v : Math.round(v); } else S.cart.splice(i, 1); refresh(); });
      inp.addEventListener("focus", () => inp.select());
    });
  }
  async function editLine(i) {
    const l = S.cart[i], cur = S.quote ? S.quote.lines[i].unit_price_kobo : 0;
    const res = await A.modal({ title: l.name, sub: "Change the price or give a discount on this item.", size: "sm",
      html: `<div class="stack"><label class="f">Discount %<input id="dp" type="number" min="0" max="100" step="0.5" value="${l.discount_pct || 0}"></label>
      <label class="f">Price for this sale (${A.cfg.cur})<input id="pr" type="number" min="0" step="0.01" value="${A.naira(l.price_kobo != null ? l.price_kobo : cur)}"></label>
      <div class="muted" style="font-size:12.5px">Big discounts or price changes ask for a manager PIN.</div></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Reset", value: "reset" }, { label: "Apply", cls: "pri", run: (b) => ({ dp: parseFloat($("#dp", b).value) || 0, pr: A.toKobo($("#pr", b).value) }) }] });
    if (!res) return;
    if (res === "reset") { l.discount_pct = 0; l.price_kobo = null; } else { l.discount_pct = res.dp; l.price_kobo = res.pr !== cur ? res.pr : l.price_kobo; }
    refresh();
  }
  function renderTotals() {
    const q = S.quote || { subtotal_kobo: 0, discount_kobo: 0, tax_kobo: 0, total_kobo: 0, inclusive: true, tax_rate: 0 };
    $("#t-sub").textContent = A.money(q.subtotal_kobo); $("#t-disc").textContent = "−" + A.money(q.discount_kobo);
    $("#t-tax").textContent = A.money(q.tax_kobo); $("#t-tax-lbl").textContent = q.inclusive ? `VAT (${q.tax_rate}%) included` : `VAT (${q.tax_rate}%) added`;
    $("#t-total").textContent = A.money(q.total_kobo);
    $("#pay-btn").disabled = !S.cart.length || !S.quote;
  }
  function reset() { S.cart = []; S.customer = null; S.cartDiscount = null; S.quote = null; S.pin = null; S.heldId = null; lastGood = null; $("#cust-lbl").textContent = "Walk-in customer"; renderLines(); renderTotals(); $("#q").focus(); }
  $("#clear-btn").addEventListener("click", async () => { if (S.cart.length && await A.confirm("Clear the basket?", "All items will be removed.", "Clear", true)) reset(); });

  // ------------- discount / customer -------------
  $("#disc-btn").addEventListener("click", async () => {
    if (!S.cart.length) return;
    const r = await A.modal({ title: "Discount on the whole basket", size: "sm",
      html: `<div class="stack"><div class="seg"><button type="button" data-t="pct" class="on">Percent %</button><button type="button" data-t="amount">Amount</button></div><label class="f">Value<input id="dv" type="number" min="0" step="0.01" inputmode="decimal"></label></div>`,
      onOpen: (b) => { A.$$(".seg button", b).forEach((x) => x.addEventListener("click", () => { A.$$(".seg button", b).forEach((y) => y.classList.toggle("on", y === x)); })); },
      actions: [{ label: "Cancel", value: null }, { label: "Remove", value: "none" }, { label: "Apply", cls: "pri", run: (b) => ({ type: $(".seg .on", b).dataset.t, value: $("#dv", b).value }) }] });
    if (!r) return;
    if (r === "none" || !+r.value) S.cartDiscount = null; else S.cartDiscount = { type: r.type, value: r.type === "amount" ? A.toKobo(r.value) : parseFloat(r.value) };
    refresh();
  });
  $("#cust-btn").addEventListener("click", async () => {
    const list = await A.get("/api/customers");
    const rows = (qs) => list.filter((c) => !qs || (c.name + " " + (c.phone || "")).toLowerCase().includes(qs.toLowerCase())).slice(0, 40).map((c) =>
      `<div class="list-row" style="cursor:pointer" data-id="${c.id}"><div class="grow">${A.esc(c.name)}<div class="muted" style="font-size:12px">${A.esc(c.phone || "no phone")} · ${c.loyalty_points} pts${c.balance_kobo ? " · owes " + A.money(c.balance_kobo) : ""}</div></div>${A.icon("chevron-right")}</div>`).join("") || A.empty("users", "No customers match.");
    await A.modal({ title: "Choose customer", size: "", html: `<input id="cq" placeholder="Search name or phone"><div id="cl" style="margin-top:10px;max-height:340px;overflow:auto">${rows("")}</div>
      <button class="btn block" id="newc" style="margin-top:10px">${A.icon("user-plus")} New customer</button>`,
      actions: [{ label: "Walk-in (no customer)", value: "none" }, { label: "Close", value: null }],
      onOpen: (b, close) => {
        const bind = () => A.$$("[data-id]", b).forEach((r) => r.addEventListener("click", () => { S.customer = list.find((c) => c.id == r.dataset.id); close(true); }));
        bind(); $("#cq", b).addEventListener("input", (e) => { $("#cl", b).innerHTML = rows(e.target.value); bind(); });
        $("#newc", b).addEventListener("click", async () => {
          const n = prompt_new(); close(false); const c = await n; if (c) { S.customer = c; setCust(); refresh(); }
        });
      } }).then((v) => { if (v === "none") S.customer = null; });
    setCust(); refresh();
  });
  const setCust = () => { $("#cust-lbl").textContent = S.customer ? S.customer.name + (S.customer.loyalty_points ? ` · ${S.customer.loyalty_points} pts` : "") : "Walk-in customer"; };
  async function prompt_new() {
    const v = await A.modal({ title: "New customer", size: "sm", html: `<div class="stack"><label class="f">Name<input name="name"></label><label class="f">Phone<input name="phone" inputmode="tel"></label></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Save", cls: "pri", run: async (b) => { const d = A.form(b); const r = await A.post("/api/customers", d); const l = await A.get("/api/customers?q=" + encodeURIComponent(d.name)); return l.find((c) => c.id === r.id); } }] });
    return v;
  }

  // ------------- held baskets -------------
  async function loadHeld() { try { S.held = await A.get("/api/pos/held"); $("#held-n").textContent = S.held.length; } catch (e) {} }
  $("#hold-btn").addEventListener("click", async () => {
    if (!S.cart.length) return A.toast("Nothing to hold.", "err");
    try { await A.post("/api/pos/held", { ...payload(), label: S.customer ? S.customer.name : "" }); A.toast("Basket parked. Recall it from “Held”."); reset(); loadHeld(); } catch (e) { A.fail(e); }
  });
  $("#held-btn").addEventListener("click", async () => {
    await loadHeld();
    if (!S.held.length) return A.toast("No held baskets.");
    const pick = await A.modal({ title: "Held baskets", html: S.held.map((h) => `<div class="list-row" data-id="${h.id}" style="cursor:pointer"><div class="grow"><b>${A.esc(h.label || "Basket")}</b><div class="muted" style="font-size:12px">${h.count} items · ${A.dt(h.created_at)}</div></div><button class="btn sm bad" data-del="${h.id}">${A.icon("trash-2", "sm")}</button></div>`).join(""),
      onOpen: (b, close) => {
        A.$$("[data-id]", b).forEach((r) => r.addEventListener("click", (e) => { if (e.target.closest("[data-del]")) return; close(+r.dataset.id); }));
        A.$$("[data-del]", b).forEach((d) => d.addEventListener("click", async () => { await A.del("/api/pos/held/" + d.dataset.del); d.closest(".list-row").remove(); loadHeld(); }));
      } });
    if (!pick) return;
    const h = S.held.find((x) => x.id === pick);
    if (S.cart.length && !(await A.confirm("Replace the current basket?", "The items now in the basket will be removed.", "Replace", true))) return;
    reset();
    try {
      const r = await A.post("/api/pos/quote", { items: h.cart.items, cart_discount: h.cart.cart_discount });
      if (r.need_pin) throw new Error("This held basket has a discount that needs a manager PIN. Recall it as a manager.");
      S.cart = r.lines.map((l, i) => ({ product_id: l.product_id, name: l.name, unit: l.unit, is_weighed: l.is_weighed, qty: l.qty, price_kobo: h.cart.items[i].price_kobo || null, discount_pct: h.cart.items[i].discount_pct || 0 }));
      S.cartDiscount = h.cart.cart_discount || null; S.heldId = h.id;
      if (h.customer_id) { const c = await A.get("/api/customers/" + h.customer_id); S.customer = c; setCust(); }
      refresh();
    } catch (e) { A.fail(e); }
  });

  // ------------- shift -------------
  async function loadShift() {
    try { S.shift = await A.get("/api/shift"); } catch (e) { return; }
    $("#shift-bar").classList.toggle("hide", !!S.shift.open);
  }
  $("#open-shift").addEventListener("click", async () => {
    const f = await A.modal({ title: "Open your shift", sub: "Count the cash in your drawer and enter it. This is your opening float.", size: "sm",
      html: `<label class="f">Cash in drawer (${A.cfg.cur})<input id="fl" type="number" min="0" step="0.01" value="0" inputmode="decimal"></label>`,
      actions: [{ label: "Cancel", value: null }, { label: "Open shift", cls: "pri", run: async (b) => { await A.post("/api/shift/open", { float: $("#fl", b).value }); return true; } }] });
    if (f) { A.toast("Shift opened. Happy selling!"); loadShift(); }
  });

  // ------------- paying -------------
  const METHODS = [["cash", "Cash", "banknote"], ["card", "Card / POS", "credit-card"], ["transfer", "Transfer", "smartphone"], ["credit", "On credit", "hand-coins"], ["points", "Points", "star"]];
  async function pay() {
    if (!S.quote) return;
    const total = S.quote.total_kobo;
    const rows = METHODS.filter(([m]) => S.customer || (m !== "credit" && m !== "points")).map(([m, lbl, ic]) =>
      `<label class="f"><span>${A.icon(ic, "sm")} ${lbl}</span><input data-m="${m}" type="number" min="0" step="0.01" inputmode="decimal" placeholder="0.00"></label>`).join("");
    const quick = [500, 1000, 2000, 5000, 10000].map((v) => `<button type="button" class="btn sm" data-q="${v}">${A.cfg.cur}${v.toLocaleString()}</button>`).join("");
    const res = await A.modal({ title: "Take payment", size: "", html: `
      <div class="row sp"><span class="muted">Total to pay</span><span class="big-num">${A.money(total)}</span></div>
      <div class="quick" style="margin:10px 0"><button type="button" class="btn sm" data-q="exact">Exact cash</button>${quick}<button type="button" class="btn sm" data-q="card">Full card</button><button type="button" class="btn sm" data-q="transfer">Full transfer</button></div>
      <div class="form">${rows}<label class="f full">Reference (optional — card slip / transfer ref)<input id="ref" maxlength="60"></label></div>
      <div class="card" style="margin-top:12px;padding:12px"><div class="row sp"><span>Received</span><b id="rec">${A.money(0)}</b></div><div class="row sp"><span id="bl-lbl">Still to pay</span><b id="bl" style="font-size:20px">${A.money(total)}</b></div></div>`,
      actions: [{ label: "Back", value: null }, { label: "Complete sale", cls: "pri", run: (b) => doCheckout(b, total) }],
      onOpen: (b) => {
        const upd = () => { const got = A.$$("[data-m]", b).reduce((a, i) => a + A.toKobo(i.value), 0), diff = got - total;
          $("#rec", b).textContent = A.money(got); $("#bl-lbl", b).textContent = diff >= 0 ? "Change to give" : "Still to pay"; $("#bl", b).textContent = A.money(Math.abs(diff)); $("#bl", b).style.color = diff >= 0 ? "var(--ok)" : "var(--warn)"; };
        A.$$("[data-m]", b).forEach((i) => i.addEventListener("input", upd));
        A.$$("[data-q]", b).forEach((x) => x.addEventListener("click", () => {
          A.$$("[data-m]", b).forEach((i) => (i.value = ""));
          const t = x.dataset.q;
          if (t === "exact") $("[data-m=cash]", b).value = A.naira(total); else if (t === "card") $("[data-m=card]", b).value = A.naira(total); else if (t === "transfer") $("[data-m=transfer]", b).value = A.naira(total); else $("[data-m=cash]", b).value = t;
          upd();
        }));
        $("[data-m=cash]", b).focus();
      } });
    if (res && res.sale_id) done(res);
  }
  async function doCheckout(b, total) {
    const pays = A.$$("[data-m]", b).map((i) => ({ method: i.dataset.m, amount_kobo: A.toKobo(i.value), reference: $("#ref", b).value })).filter((p) => p.amount_kobo > 0);
    if (!pays.length) { A.toast("Enter how much the customer is paying.", "err"); return false; }
    const r = await A.withPin((pin) => A.post("/api/pos/checkout", { ...payload(), pin: pin || S.pin, payments: pays, held_id: S.heldId }));
    if (!r) return false;
    return r;
  }
  async function done(r) {
    const again = await A.modal({ title: "Sale complete ✓", size: "sm", html: `<div class="stack" style="text-align:center"><div class="muted">${A.esc(r.receipt_no)}</div><div class="big-num">${A.money(r.total_kobo)}</div>
      ${r.change_kobo ? `<div class="card" style="padding:14px"><div class="muted">Give change</div><div class="big-num" style="color:var(--ok)">${A.money(r.change_kobo)}</div></div>` : ""}
      ${r.points_earned ? `<div class="pill ok" style="justify-self:center">+${r.points_earned} loyalty points</div>` : ""}</div>`,
      actions: [{ label: "Print receipt", value: "print" }, { label: "New sale", cls: "pri", value: "new" }] });
    if (again === "print") A.printReceipt(r.sale_id);
    reset(); loadProducts(); loadHeld(); loadShift();
  }
  $("#pay-btn").addEventListener("click", pay);

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input,textarea,select") && e.key !== "F9" && e.key !== "F4") { return; }
    if (e.key === "/") { e.preventDefault(); $("#q").focus(); }
    if (e.key === "F9") { e.preventDefault(); if (!$("#pay-btn").disabled) pay(); }
    if (e.key === "F4") { e.preventDefault(); $("#hold-btn").click(); }
  });
  const mb2 = $("#menu-btn2"); if (mb2) mb2.addEventListener("click", () => $("#menu-btn").click());

  loadCats(); loadProducts(); loadHeld(); loadShift(); renderLines(); renderTotals(); $("#q").focus();
})();
