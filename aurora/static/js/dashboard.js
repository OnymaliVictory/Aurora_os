(async function () {
  A.$("#today-lbl").textContent = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  let d;
  try { d = await A.get("/api/dashboard"); } catch (e) { return A.fail(e); }
  A.$("#s-rev").textContent = A.money(d.today.revenue_kobo);
  A.$("#s-n").textContent = d.today.sales + (d.today.sales === 1 ? " sale" : " sales");
  A.$("#s-avg").textContent = A.money(d.today.avg_basket_kobo);
  if (A.$("#s-profit")) A.$("#s-profit").textContent = A.money(d.today.profit_kobo);
  if (A.$("#s-owed")) A.$("#s-owed").textContent = A.money(d.owed_kobo);
  if (A.$("#s-alert")) {
    const n = (d.low_stock || 0) + (d.out_of_stock || 0) + (d.expiring || 0);
    A.$("#s-alert").textContent = n;
    A.$("#s-alert-h").textContent = `${d.low_stock} low · ${d.out_of_stock} out · ${d.expiring} expiring`;
  }
  const labels = d.week.labels.map((x) => new Date(x + "T00:00").toLocaleDateString("en-GB", { weekday: "short" }));
  Charts.line(A.$("#c-week"), labels, d.week.values, { fmt: (v) => A.moneyShort(v) });
  Charts.bars(A.$("#c-hours"), d.hours.labels.map((h) => h + "h"), d.hours.values, { fmt: (v) => A.moneyShort(v) });
  const names = { cash: "Cash", card: "Card", transfer: "Transfer", credit: "On credit", points: "Points" };
  const pal = Charts.palette(); const items = Object.entries(d.mix).map(([k, v], i) => ({ label: names[k] || k, value: v, color: pal[i % pal.length] }));
  Charts.donut(A.$("#c-mix"), items, { center: A.moneyShort(items.reduce((a, b) => a + b.value, 0)), sub: "total" });
  A.$("#mix-leg").innerHTML = items.map((i) => `<span><span class="dot" style="background:${i.color}"></span>${A.esc(i.label)} ${A.money(i.value)}</span>`).join("") || '<span class="muted">No sales yet today.</span>';
  A.$("#top").innerHTML = d.top.length ? d.top.map((t, i) => `<div class="list-row"><span class="pill">${i + 1}</span><div class="grow ellip">${A.esc(t.name)}<div class="muted" style="font-size:12px">${A.qty(t.qty)} sold</div></div><b>${A.money(t.rev)}</b></div>`).join("") : A.empty("star", "Nothing sold yet today.");
  const al = A.$("#alerts");
  if (al) {
    const rows = (d.low_list || []).map((p) => `<div class="list-row"><span class="pill ${p.qty <= 0 ? "bad" : "warn"}">${p.qty <= 0 ? "Out" : "Low"}</span><div class="grow ellip">${A.esc(p.name)}</div><span class="muted">${A.qty(p.qty)} left</span></div>`)
      .concat((d.expiry_list || []).map((p) => `<div class="list-row"><span class="pill bad">Expiry</span><div class="grow ellip">${A.esc(p.name)}</div><span class="muted">${A.date(p.expiry_date)}</span></div>`));
    al.innerHTML = rows.join("") || A.empty("circle-check", "All stock looks healthy.");
  }
})();
