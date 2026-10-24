(function () {
  const d = new Date(); A.$("#from").value = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-01"; A.$("#to").value = A.today();
  const CATS = ["Rent", "Electricity / fuel", "Salaries", "Transport", "Packaging", "Repairs", "Marketing", "Taxes & levies", "Other"];
  async function load() {
    let rows; try { rows = await A.get(`/api/expenses?from=${A.$("#from").value}&to=${A.$("#to").value}`); } catch (e) { return A.fail(e); }
    A.$("#tot").textContent = A.money(rows.reduce((a, r) => a + r.amount_kobo, 0));
    A.$("#rows").innerHTML = rows.map((r) => `<tr><td>${A.date(r.paid_on)}</td><td>${A.pill(r.category)}</td><td class="muted">${A.esc(r.note || "")}</td><td class="num">${A.money(r.amount_kobo)}</td><td class="right"><button class="btn sm bad" data-id="${r.id}">${A.icon("trash-2", "sm")}</button></td></tr>`).join("") || `<tr><td colspan="5">${A.empty("hand-coins", "No expenses in this period.")}</td></tr>`;
    const by = {}; rows.forEach((r) => (by[r.category] = (by[r.category] || 0) + r.amount_kobo)); const mx = Math.max(...Object.values(by), 1);
    A.$("#cats").innerHTML = Object.entries(by).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div style="margin-bottom:12px"><div class="row sp"><span>${A.esc(k)}</span><b>${A.money(v)}</b></div><div class="bar"><i style="width:${v / mx * 100}%"></i></div></div>`).join("") || '<div class="muted">Nothing to show.</div>';
    A.$$("[data-id]").forEach((b) => b.addEventListener("click", async () => { if (await A.confirm("Delete this expense?", "", "Delete", true)) { await A.del("/api/expenses/" + b.dataset.id).catch(A.fail); load(); } }));
  }
  A.$("#from").addEventListener("change", load); A.$("#to").addEventListener("change", load);
  A.$("#add").addEventListener("click", async () => {
    const r = await A.modal({ title: "Add expense", size: "sm", html: `<div class="stack"><label class="f">Category<select name="category">${CATS.map((c) => `<option>${c}</option>`).join("")}</select></label><label class="f">Amount (${A.cfg.cur})<input name="amount" type="number" step="0.01" min="0"></label><label class="f">Date<input name="paid_on" type="date" value="${A.today()}"></label><label class="f">Note<input name="note" maxlength="160"></label></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Save", cls: "pri", run: async (b) => { await A.post("/api/expenses", A.form(b)); return true; } }] });
    if (r) { A.toast("Expense saved."); load(); }
  });
  load();
})();
