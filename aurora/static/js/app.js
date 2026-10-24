/* Aurora OS shared helpers. Everything user-typed is escaped before it touches innerHTML. */
(function () {
  const body = document.body;
  const A = (window.A = {});
  const CUR = body.dataset.cur || "₦";
  A.cfg = body.dataset;
  A.$ = (s, r) => (r || document).querySelector(s);
  A.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  A.esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  A.icon = (n, c) => `<svg class="i ${c || ""}" aria-hidden="true"><use href="/static/img/sprite.svg#${n}"/></svg>`;
  A.money = (k) => {
    k = Math.round(k || 0);
    const neg = k < 0; k = Math.abs(k);
    const n = Math.floor(k / 100), c = k % 100;
    return (neg ? "-" : "") + CUR + n.toLocaleString("en-NG") + (c ? "." + String(c).padStart(2, "0") : "");
  };
  A.moneyShort = (k) => { const n = Math.abs(k) / 100, s = k < 0 ? "-" : ""; return s + CUR + (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k" : Math.round(n)); };
  A.qty = (n) => (Math.round(n * 1000) / 1000).toLocaleString("en-NG", { maximumFractionDigits: 3 });
  A.toKobo = (v) => { const n = parseFloat(String(v).replace(/,/g, "")); return isFinite(n) ? Math.round(n * 100) : 0; };
  A.naira = (k) => (k / 100).toFixed(2);
  A.date = (s) => { if (!s) return ""; const d = new Date(s.replace(" ", "T")); return isNaN(d) ? s : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); };
  A.dt = (s) => { if (!s) return ""; const d = new Date(s.replace(" ", "T")); return isNaN(d) ? s : d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); };
  A.today = () => { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
  A.daysFrom = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
  A.debounce = (f, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => f(...a), ms); }; };
  A.pill = (text, kind) => `<span class="pill ${kind || ""}">${A.esc(text)}</span>`;

  // ---- talking to the app ----
  A.api = async (method, url, data) => {
    const opt = { method, headers: { "X-CSRF-Token": body.dataset.csrf, "X-Requested-With": "fetch" } };
    if (data !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(data); }
    let r;
    try { r = await fetch(url, opt); } catch (e) { throw new Error("Can't reach Aurora OS. Is the program still running?"); }
    if (r.status === 401) { location.href = "/login"; throw new Error("Please sign in again."); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) throw new Error(j.error || "Something went wrong.");
    return j;
  };
  A.get = (u) => A.api("GET", u);
  A.post = (u, d) => A.api("POST", u, d || {});
  A.put = (u, d) => A.api("PUT", u, d || {});
  A.del = (u) => A.api("DELETE", u);

  // ---- toasts ----
  A.toast = (msg, type) => {
    const t = document.createElement("div");
    t.className = "toast " + (type === "err" ? "err" : "ok");
    t.innerHTML = A.icon(type === "err" ? "circle-x" : "circle-check") + `<div>${A.esc(msg)}</div>`;
    A.$("#toasts").appendChild(t);
    setTimeout(() => t.remove(), type === "err" ? 6000 : 3200);
  };
  A.fail = (e) => A.toast(e && e.message ? e.message : String(e), "err");

  // ---- modal ----
  A.modal = ({ title, sub, html, actions, size, onOpen }) => new Promise((resolve) => {
    const ov = document.createElement("div");
    ov.className = "overlay";
    const acts = (actions || [{ label: "Close", value: null }]).map((a, i) => `<button type="button" class="btn ${a.cls || ""}" data-i="${i}">${A.esc(a.label)}</button>`).join("");
    ov.innerHTML = `<div class="modal ${size || ""}" role="dialog" aria-modal="true"><h2>${A.esc(title || "")}</h2>${sub ? `<div class="sub">${A.esc(sub)}</div>` : ""}<div class="mbody">${html || ""}</div><div class="acts">${acts}</div></div>`;
    document.body.appendChild(ov);
    const box = ov.firstChild;
    const close = (v) => { document.removeEventListener("keydown", esc); ov.remove(); resolve(v); };
    const esc = (e) => { if (e.key === "Escape") close(undefined); };
    document.addEventListener("keydown", esc);
    ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(undefined); });
    A.$$("[data-i]", box).forEach((b) => b.addEventListener("click", async () => {
      const a = (actions || [{ value: null }])[+b.dataset.i];
      if (a.run) {                      // run() may validate; return false to keep the dialog open
        b.disabled = true;
        try { const out = await a.run(box); if (out !== false) close(out === undefined ? a.value : out); } catch (e) { A.fail(e); }
        b.disabled = false;
      } else close(a.value);
    }));
    if (onOpen) onOpen(box, close);
    const first = A.$("input:not([type=hidden]),select,textarea", box); if (first) first.focus();
    box.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") { const p = A.$(".acts .btn.pri", box); if (p) { e.preventDefault(); p.click(); } } });
  });
  A.confirm = (title, sub, label, danger) => A.modal({ title, sub, size: "sm", actions: [{ label: "Cancel", value: false }, { label: label || "Yes", value: true, cls: danger ? "bad" : "pri" }] });
  A.pin = async (reason) => {
    const v = await A.modal({ title: "Manager approval", sub: (reason || "This") + " needs a manager or owner PIN.", size: "sm",
      html: `<label class="f">PIN<input id="pin-in" type="password" inputmode="numeric" autocomplete="off" maxlength="8"></label>`,
      actions: [{ label: "Cancel", value: null }, { label: "Approve", cls: "pri", run: (b) => { const v = A.$("#pin-in", b).value; if (!v) { A.toast("Enter the PIN.", "err"); return false; } return v; } }] });
    return v || null;
  };
  // Calls fn(pin) and, if the server says a PIN is needed, asks once and retries.
  A.withPin = async (fn) => {
    let r = await fn(null);
    if (r && r.need_pin) { const pin = await A.pin(r.reason); if (!pin) return null; r = await fn(pin); }
    return r;
  };
  A.form = (box) => { const o = {}; A.$$("[name]", box).forEach((e) => { o[e.name] = e.type === "checkbox" ? e.checked : e.value; }); return o; };
  A.download = (url) => { const a = document.createElement("a"); a.href = url; a.click(); };
  A.empty = (icon, msg) => `<div class="empty">${A.icon(icon || "info")}${A.esc(msg)}</div>`;
  A.printReceipt = (id) => { const w = window.open("/receipt/" + id + "?print=1", "receipt", "width=420,height=720"); if (!w) A.toast("Allow pop-ups to print the receipt.", "err"); };

  // ---- theme, menu, alerts ----
  const setTheme = (t) => {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("aurora_os_theme", t); } catch (e) {}
    const l = A.$("#theme-lbl"); if (l) l.textContent = t === "dark" ? "Light mode" : "Northern lights";
    const b = A.$("#theme-btn"); if (b) b.querySelector("use").setAttribute("href", "/static/img/sprite.svg#" + (t === "dark" ? "sun" : "moon"));
    window.dispatchEvent(new Event("themechange"));
  };
  const tb = A.$("#theme-btn");
  if (tb) { setTheme(document.documentElement.getAttribute("data-theme")); tb.addEventListener("click", () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark")); }
  const mb = A.$("#menu-btn");
  if (mb) { mb.addEventListener("click", (e) => { e.stopPropagation(); body.classList.toggle("nav-open"); }); document.addEventListener("click", (e) => { if (body.classList.contains("nav-open") && !e.target.closest("#side")) body.classList.remove("nav-open"); }); }
  const badge = async () => {
    const el = A.$("#notif-badge"); if (!el) return;
    try { const r = await A.get("/api/notifications/count"); el.textContent = r.unread > 99 ? "99+" : r.unread; el.classList.toggle("hide", !r.unread); } catch (e) { /* ignore */ }
  };
  badge(); setInterval(badge, 60000);
})();
