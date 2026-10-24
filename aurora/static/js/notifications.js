(function () {
  const ic = { low_stock: ["triangle-alert", "warn"], out_of_stock: ["ban", "bad"], expiring: ["clock", "warn"], expired: ["circle-x", "bad"], cash_difference: ["wallet", "warn"], info: ["info", "info"] };
  async function load() {
    let r; try { r = await A.get("/api/notifications"); } catch (e) { return A.fail(e); }
    A.$("#list").innerHTML = r.items.map((n) => { const [i, k] = ic[n.kind] || ic.info; return `<div class="list-row" style="${n.is_read ? "opacity:.55" : ""}"><span class="pill ${k}">${A.icon(i, "sm")}</span><div class="grow"><b>${A.esc(n.title)}</b><div class="muted">${A.esc(n.message || "")}</div></div><span class="muted" style="font-size:12px">${A.dt(n.created_at)}</span>${n.link ? `<a class="btn sm" href="${A.esc(n.link)}" data-id="${n.id}">View</a>` : ""}${n.is_read ? "" : `<button class="btn sm" data-r="${n.id}">${A.icon("check", "sm")}</button>`}</div>`; }).join("") || A.empty("bell", "No alerts. Everything is fine.");
    A.$$("[data-r]").forEach((b) => b.addEventListener("click", async () => { await A.post("/api/notifications/read", { id: b.dataset.r }); load(); }));
  }
  A.$("#readall").addEventListener("click", async () => { await A.post("/api/notifications/read", {}); load(); });
  load();
})();
