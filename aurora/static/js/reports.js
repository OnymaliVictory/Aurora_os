(function () {
  const $ = A.$, profit = A.cfg.profit === "1";
  const set = (n) => { const d = new Date(); let f = new Date(); if (n === "month") f = new Date(d.getFullYear(), d.getMonth(), 1); else f.setDate(d.getDate() - +n); const iso = (x) => x.getFullYear() + "-" + String(x.getMonth() + 1).padStart(2, "0") + "-" + String(x.getDate()).padStart(2, "0"); $("#from").value = iso(f); $("#to").value = iso(d); };
  A.$$("#quick button").forEach((b) => b.addEventListener("click", () => { A.$$("#quick button").forEach((x) => x.classList.toggle("on", x === b)); set(b.dataset.d); load(); }));
  set(29); $("#from").addEventListener("change", load); $("#to").addEventListener("change", load);
  $("#csv").addEventListener("click", () => A.download(`/api/reports/sales.csv?from=${$("#from").value}&to=${$("#to").value}`));
  $("#print").addEventListener("click", () => window.print());
  const tile = (l, v, h, k) => `<div class="card stat ${k || ""}"><div class="lbl">${l}</div><div class="val">${v}</div><div class="hint">${h || ""}</div></div>`;
  async function load() {
    let r; try { r = await A.get(`/api/reports/summary?from=${$("#from").value}&to=${$("#to").value}`); } catch (e) { return A.fail(e); }
    $("#range-lbl").textContent = `${A.date(r.from)} – ${A.date(r.to)}`;
    $("#tiles").innerHTML = tile("Revenue", A.money(r.revenue_kobo), `${r.sales} sales · avg ${A.money(r.avg_basket_kobo)}`) +
      (profit ? tile("Gross profit", A.money(r.gross_profit_kobo), `${r.margin_pct}% margin`) + tile("Net profit", A.money(r.net_profit_kobo), `after ${A.money(r.expenses_kobo)} expenses`, r.net_profit_kobo < 0 ? "bad" : "") : tile("VAT collected", A.money(r.tax_kobo))) +
      tile("Refunds", A.money(r.refunded_kobo), `${r.refunds} refunds`, r.refunded_kobo ? "warn" : "");
    const lab = r.daily.labels.map((x) => x.slice(5)); Charts.line($("#c-day"), lab, r.daily.values, { fmt: (v) => A.moneyShort(v) });
    const pal = Charts.palette(), cats = r.by_category.map((c, i) => ({ label: c.name, value: c.rev, color: c.color || pal[i % pal.length] }));
    Charts.donut($("#c-cat"), cats, { center: A.moneyShort(r.revenue_kobo), sub: "revenue" });
    $("#cat-leg").innerHTML = cats.map((c) => `<span><span class="dot" style="background:${A.esc(c.color)}"></span>${A.esc(c.label)} ${A.money(c.value)}</span>`).join("");
    $("#top").innerHTML = r.top.map((t) => `<tr><td>${A.esc(t.name)}</td><td class="num">${A.qty(t.qty)}</td><td class="num">${A.money(t.rev)}</td>${profit ? `<td class="num">${A.money(t.profit)}</td>` : ""}</tr>`).join("") || `<tr><td colspan="4" class="muted">No sales in this period.</td></tr>`;
    const mx = Math.max(...r.by_cashier.map((c) => c.rev), 1);
    $("#cashier").innerHTML = r.by_cashier.map((c) => `<div style="margin-bottom:10px"><div class="row sp"><span>${A.esc(c.name)} <span class="muted">(${c.n} sales)</span></span><b>${A.money(c.rev)}</b></div><div class="bar"><i style="width:${c.rev / mx * 100}%"></i></div></div>`).join("") || '<div class="muted">No data.</div>';
    const names = { cash: "Cash", card: "Card", transfer: "Transfer", credit: "On credit", points: "Points" }, tot = Object.values(r.mix).reduce((a, b) => a + b, 0) || 1;
    $("#mix").innerHTML = Object.entries(r.mix).map(([k, v]) => `<div style="margin-bottom:10px"><div class="row sp"><span>${names[k] || k}</span><b>${A.money(v)} <span class="muted">${Math.round(v / tot * 100)}%</span></b></div><div class="bar"><i style="width:${v / tot * 100}%"></i></div></div>`).join("") || '<div class="muted">No data.</div>';
    if (profit) {
      $("#exp").innerHTML = (r.expenses_by.map((e) => `<div class="row sp list-row"><span>${A.esc(e.name)}</span><b>${A.money(e.a)}</b></div>`).join("") || '<div class="muted">No expenses recorded.</div>') + `<div class="row sp" style="margin-top:10px"><b>Total</b><b>${A.money(r.expenses_kobo)}</b></div>`;
      $("#stockval").innerHTML = `<div class="row sp"><span>Stock at cost</span><b>${A.money(r.stock_cost_kobo)}</b></div><div class="row sp"><span>Stock at selling price</span><b>${A.money(r.stock_retail_kobo)}</b></div><div class="row sp"><span>Potential profit on shelf</span><b style="color:var(--ok)">${A.money(r.stock_retail_kobo - r.stock_cost_kobo)}</b></div>`;
      $("#dead").innerHTML = r.dead_stock.map((p) => `<div class="list-row"><div class="grow ellip">${A.esc(p.name)}</div><span class="muted">${A.qty(p.qty)} units</span><b>${A.money(p.tied)}</b></div>`).join("") || '<div class="muted">Nothing stuck — every product moved.</div>';
    }
  }
  load();
})();
