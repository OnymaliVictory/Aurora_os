(function () {
  async function load() {
    let rows; try { rows = await A.get("/api/audit?q=" + encodeURIComponent(A.$("#q").value)); } catch (e) { return A.fail(e); }
    const kind = (a) => (/void|refund|delete/.test(a) ? "bad" : /login|setup/.test(a) ? "info" : /sale|create/.test(a) ? "ok" : "");
    A.$("#rows").innerHTML = rows.map((r) => `<tr><td class="nowrap muted">${A.dt(r.created_at)}</td><td>${A.esc(r.user_name)}</td><td>${A.pill(r.action, kind(r.action))}</td><td>${A.esc(r.description)}</td></tr>`).join("") || `<tr><td colspan="4">${A.empty("history", "Nothing here yet.")}</td></tr>`;
  }
  A.$("#q").addEventListener("input", A.debounce(load)); load();
})();
