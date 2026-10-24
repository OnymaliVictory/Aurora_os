(function () {
  const canEdit = !!A.$("#add"); let rows = [];
  async function load() {
    try { rows = await A.get("/api/users"); } catch (e) { return A.fail(e); }
    A.$("#rows").innerHTML = rows.map((u) => `<tr ${canEdit ? 'class="click"' : ""} data-id="${u.id}"><td><b>${A.esc(u.name)}</b><div class="muted" style="font-size:12px">${A.esc(u.phone || "")}</div></td><td>${A.esc(u.username)}</td><td>${A.pill(u.role, u.role === "owner" ? "info" : u.role === "manager" ? "ok" : "")}${u.has_pin ? ' <span class="muted" title="Has an approval PIN">' + A.icon("key", "sm") + "</span>" : ""}</td><td class="muted">${u.last_login_at ? A.dt(u.last_login_at) : "never"}</td><td>${u.is_active ? A.pill("Active", "ok") : A.pill("Disabled", "bad")}</td><td class="right">${canEdit ? `<button class="btn sm">${A.icon("pencil", "sm")}</button>` : ""}</td></tr>`).join("");
    if (canEdit) A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => edit(rows.find((x) => x.id == tr.dataset.id))));
  }
  async function edit(u) {
    const v = u || { role: "cashier", is_active: 1 };
    const r = await A.modal({ title: u ? "Edit " + u.name : "Add staff", html: `<div class="form"><label class="f">Name<input name="name" value="${A.esc(v.name || "")}"></label><label class="f">Username<input name="username" value="${A.esc(v.username || "")}" autocomplete="off"></label>
      <label class="f">Role<select name="role">${["cashier", "manager", "owner"].map((r) => `<option ${v.role === r ? "selected" : ""}>${r}</option>`).join("")}</select></label><label class="f">Phone<input name="phone" value="${A.esc(v.phone || "")}"></label>
      <label class="f">${u ? "New password (leave blank to keep)" : "Password (6+ characters)"}<input name="password" type="password" autocomplete="new-password"></label>
      <label class="f">${u ? "New PIN (managers/owners)" : "PIN (managers/owners, 4–8 digits)"}<input name="pin" type="password" inputmode="numeric" maxlength="8" autocomplete="off"></label>
      ${u ? `<label class="chk full"><input type="checkbox" name="is_active" ${v.is_active ? "checked" : ""}> Account is active</label>` : ""}</div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Save", cls: "pri", run: async (b) => { const d = A.form(b); if (u) await A.put("/api/users/" + u.id, d); else await A.post("/api/users", d); return true; } }] });
    if (r) { A.toast("Saved."); load(); }
  }
  if (canEdit) A.$("#add").addEventListener("click", () => edit(null));
  load();
})();
