(function () {
  const f = A.$("#f"), err = A.$("#err");
  const show = (n) => { A.$("#p1").classList.toggle("hide", n !== 1); A.$("#p2").classList.toggle("hide", n !== 2); A.$("#s2").classList.toggle("on", n === 2); };
  A.$("#next").addEventListener("click", () => { if (!A.$("[name=store_name]").value.trim()) { A.toast("Enter your shop name.", "err"); return; } show(2); });
  A.$("#back").addEventListener("click", () => show(1));
  f.addEventListener("submit", async (e) => {
    e.preventDefault(); err.classList.add("hide"); A.$("#go").disabled = true;
    try { await A.post("/api/setup", A.form(f)); location.href = "/"; }
    catch (x) { err.textContent = x.message; err.classList.remove("hide"); A.$("#go").disabled = false; }
  });
})();
