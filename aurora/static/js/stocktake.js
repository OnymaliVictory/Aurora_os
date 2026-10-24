(function () {
  const $ = A.$, showCost = A.cfg.cost === "1";
  async function load() {
    let rows; try { rows = await A.get("/api/stocktakes"); } catch (e) { return A.fail(e); }
    $("#rows").innerHTML = rows.map((t) => `<tr class="click" data-id="${t.id}"><td><b>${A.esc(t.name)}</b></td><td>${A.pill(t.status, t.status === "open" ? "warn" : t.status === "applied" ? "ok" : "bad")}</td><td class="muted">${A.dt(t.created_at)}</td><td class="num">${t.counted} / ${t.lines}</td></tr>`).join("") || `<tr><td colspan="4">${A.empty("clipboard-check", "No stock counts yet.")}</td></tr>`;
    A.$$("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => open(+tr.dataset.id)));
  }
  $("#add").addEventListener("click", async () => {
    const cats = await A.get("/api/categories");
    const r = await A.modal({ title: "Start a stock count", size: "sm", sub: "Aurora lists what it thinks you have. You type what's really on the shelf.", html: `<div class="stack"><label class="f">Name<input name="name" value="Count ${A.today()}"></label><label class="f">Which products?<select name="category_id"><option value="">Everything</option>${cats.map((c) => `<option value="${c.id}">${A.esc(c.name)}</option>`).join("")}</select></label></div>`,
      actions: [{ label: "Cancel", value: null }, { label: "Start", cls: "pri", run: async (b) => (await A.post("/api/stocktakes", A.form(b))).id }] });
    if (r) { load(); open(r); }
  });
  async function open(id) {
    const t = await A.get("/api/stocktakes/" + id).catch(A.fail); if (!t) return;
    const editable = t.status === "open";
    const draw = (b) => { const term = ($("#fq", b).value || "").toLowerCase(), only = $("#fo", b).checked;
      $("#tb", b).innerHTML = t.items.filter((i) => (!term || i.name.toLowerCase().includes(term) || (i.barcode || "").includes(term)) && (!only || i.counted_qty == null)).map((i) => { const diff = i.counted_qty == null ? null : Math.round((i.counted_qty - i.expected_qty) * 1000) / 1000;
        return `<tr data-p="${i.product_id}"><td>${A.esc(i.name)}<div class="muted" style="font-size:12px">${A.esc(i.barcode || "")}</div></td><td class="num">${A.qty(i.expected_qty)}</td><td class="num">${editable ? `<input type="number" min="0" step="0.001" value="${i.counted_qty == null ? "" : i.counted_qty}" style="width:100px">` : i.counted_qty == null ? "—" : A.qty(i.counted_qty)}</td><td class="num" id="d${i.product_id}">${diff == null ? "" : diff === 0 ? A.pill("OK", "ok") : A.pill((diff > 0 ? "+" : "") + A.qty(diff), diff < 0 ? "bad" : "warn")}</td></tr>`; }).join("");
      if (editable) A.$$("#tb input", b).forEach((inp) => inp.addEventListener("change", async () => { const pid = +inp.closest("tr").dataset.p, it = t.items.find((x) => x.product_id === pid); try { await A.put(`/api/stocktakes/${id}/count`, { product_id: pid, counted: inp.value }); it.counted_qty = inp.value === "" ? null : parseFloat(inp.value); const diff = it.counted_qty == null ? null : Math.round((it.counted_qty - it.expected_qty) * 1000) / 1000; $("#d" + pid, b).innerHTML = diff == null ? "" : diff === 0 ? A.pill("OK", "ok") : A.pill((diff > 0 ? "+" : "") + A.qty(diff), diff < 0 ? "bad" : "warn"); prog(b); } catch (e) { A.fail(e); } }));
      prog(b); };
    const prog = (b) => { const n = t.items.filter((i) => i.counted_qty != null).length; $("#pg", b).textContent = `${n} of ${t.items.length} counted`; };
    const r = await A.modal({ title: t.name, size: "wide", sub: editable ? "Type the quantity you counted. Leave blank if you didn't count it — it won't change." : "This count is " + t.status + ".", html: `<div class="row" style="margin-bottom:10px"><div class="search"><span>${A.icon("search")}</span><input id="fq" placeholder="Filter…"></div><label class="chk"><input type="checkbox" id="fo"> Only not yet counted</label><b id="pg"></b></div><div class="tbl-wrap" style="max-height:52vh"><table><thead><tr><th>Product</th><th class="num">System says</th><th class="num">You counted</th><th class="num">Difference</th></tr></thead><tbody id="tb"></tbody></table></div>`,
      onOpen: (b) => { draw(b); $("#fq", b).addEventListener("input", () => draw(b)); $("#fo", b).addEventListener("change", () => draw(b)); },
      actions: [{ label: "Close", value: null }].concat(editable ? [{ label: "Cancel count", cls: "bad", value: "cancel" }, { label: "Apply to stock", cls: "pri", run: async () => { const c = t.items.filter((i) => i.counted_qty != null).length; if (!c) throw new Error("Count at least one product first."); if (!(await A.confirm("Apply this count?", `${c} counted products will be corrected to what you counted.`, "Apply"))) return false; return await A.post(`/api/stocktakes/${id}/apply`, {}); } }] : []) });
    if (r === "cancel") { await A.post(`/api/stocktakes/${id}/cancel`, {}); load(); }
    else if (r && r.ok) { await A.modal({ title: "Stock corrected ✓", size: "sm", html: `<p>${r.changed} products adjusted.</p>${showCost ? `<p>Shrinkage (missing stock) worth <b>${A.money(r.shrinkage_kobo)}</b>.</p>` : ""}` }); load(); } else load();
  }
  load();
})();
