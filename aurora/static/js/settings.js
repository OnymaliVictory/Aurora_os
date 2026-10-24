(function () {
  const $ = A.$, box = $("#sf");
  async function load() {
    const s = await A.get("/api/settings").catch(A.fail); if (!s) return;
    A.$$("[name]", box).forEach((e) => { if (e.type === "checkbox") e.checked = s[e.name] === "1"; else e.value = s[e.name] == null ? "" : s[e.name]; });
    bks();
  }
  $("#save").addEventListener("click", async () => { try { await A.put("/api/settings", A.form(box)); A.toast("Settings saved."); setTimeout(() => location.reload(), 500); } catch (e) { A.fail(e); } });
  async function bks() {
    const rows = await A.get("/api/backups").catch(() => []);
    $("#bks").innerHTML = rows.map((b) => `<tr><td>${A.esc(b.name)}</td><td class="muted">${A.esc(b.when)}</td><td class="num">${(b.size / 1024).toFixed(0)} KB</td><td class="right nowrap"><button class="btn sm" data-dl="${A.esc(b.name)}">${A.icon("download", "sm")} Save copy</button> <button class="btn sm bad" data-rs="${A.esc(b.name)}">${A.icon("rotate-ccw", "sm")} Restore</button></td></tr>`).join("") || `<tr><td colspan="4">${A.empty("database", "No backups yet.")}</td></tr>`;
    A.$$("[data-dl]").forEach((x) => x.addEventListener("click", () => A.download(`/api/backups/${encodeURIComponent(x.dataset.dl)}/download`)));
    A.$$("[data-rs]").forEach((x) => x.addEventListener("click", async () => {
      const r = await A.modal({ title: "Restore this backup?", size: "sm", sub: "Everything entered since then will be replaced. A safety copy of today's data is made first.", html: `<label class="f">Type RESTORE to confirm<input id="cf" autocomplete="off"></label>`, actions: [{ label: "Cancel", value: null }, { label: "Restore", cls: "bad", run: async (b) => { await A.post(`/api/backups/${encodeURIComponent(x.dataset.rs)}/restore`, { confirm: $("#cf", b).value }); return true; } }] });
      if (r) { A.toast("Restored. Signing you out…"); setTimeout(() => (location.href = "/login"), 1200); }
    }));
  }
  $("#bk").addEventListener("click", async () => { try { await A.post("/api/backups", {}); A.toast("Backup saved."); bks(); } catch (e) { A.fail(e); } });
  $("#demo").addEventListener("click", async () => { if (await A.confirm("Load sample products?", "Adds about 30 sample products and 3 customers. Your own products stay untouched.", "Load")) { try { await A.post("/api/demo", {}); A.toast("Sample products added."); } catch (e) { A.fail(e); } } });
  load();
})();
