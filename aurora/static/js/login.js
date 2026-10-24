(function () {
  const f = A.$("#f"), err = A.$("#err"), go = A.$("#go");
  f.addEventListener("submit", async (e) => {
    e.preventDefault(); err.classList.add("hide"); go.disabled = true;
    try {
      const d = A.form(f); d.next = new URLSearchParams(location.search).get("next") || "";
      const r = await A.post("/api/login", d);
      location.href = r.next;
    } catch (x) { err.textContent = x.message; err.classList.remove("hide"); go.disabled = false; }
  });
})();
