(function () {
  let rows = [];
  async function load() {
    try { rows = await A.get("/api/suppliers"); } catch (e) { return A.fail(e); }
    A.$("#rows").innerHTML = rows.map((s) => `<tr class="click" data-id="${s.id}"><td><b>${A.esc(s.name)}</b><div class="muted" style="font-size:12px">${A.esc(s.company || "")}</div></td>
      <td>${A.esc(s.contact_person || "")}<div class="muted" style="font-size:12px">${A.esc(s.phone || "")} ${A.esc(s.email || "")}</div></td><td>${A.esc(s.payment_terms || "—")}</td>
      <td class="num">${s.products}</td><td class="num">${s.owed_kobo > 0 ? A.pill(A.money(s.owed_kobo), "warn") : '<span class="faint">—</span>'}</td><td class="right"><button class="btn sm">${A.icon("pencil", "sm")}</button></td></tr>`).join("") || `<tr><td colspan="6">${A.empty("truck", "No suppliers yet.")}</td></tr>`;
    A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => edit(rows.find((x) => x.id == tr.dataset.id))));
  }
  async function edit(s) {
    const v = s || {};
    const f = (n, l, ph) => `<label class="f">${l}<input name="${n}" value="${A.esc(v[n] || "")}" placeholder="${ph || ""}"></label>`;
    const r = await A.modal({ title: s ? "Edit supplier" : "Add supplier", html: `<div class="form">${f("name", "Name")}${f("company", "Company")}${f("contact_person", "Contact person")}${f("phone", "Phone")}${f("email", "Email")}${f("payment_terms", "Payment terms", "e.g. 14 days")}<label class="f full">Address<input name="address" value="${A.esc(v.address || "")}"></label></div>`,
      actions: [{ label: "Cancel", value: null }].concat(s ? [{ label: "Remove", cls: "bad", value: "del" }] : []).concat([{ label: "Save", cls: "pri", run: async (b) => { const d = A.form(b); if (s) await A.put("/api/suppliers/" + s.id, d); else await A.post("/api/suppliers", d); return true; } }]) });
    if (r === "del" && await A.confirm("Remove " + s.name + "?", "", "Remove", true)) { await A.del("/api/suppliers/" + s.id).catch(A.fail); load(); } else if (r === true) { A.toast("Saved."); load(); }
  }
  A.$("#add").addEventListener("click", () => edit(null));
  load();
})();
