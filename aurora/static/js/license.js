(function () {
  const $ = A.$;
  const go = $("#go"), site = $("#site");
  if (go) go.addEventListener("click", async () => {
    try { await A.post("/api/license", { key: $("#key").value }); A.toast("Subscription saved. Thank you!"); setTimeout(() => (location.href = "/"), 900); } catch (e) { A.fail(e); }
  });
  if (site) site.addEventListener("click", async () => { try { await A.post("/api/license/open-site", {}); } catch (e) { A.fail(e); } });
})();
