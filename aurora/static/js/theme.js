// Runs before the page paints so there is no white flash. Dark (northern lights) is the default.
(function () {
  var t = "dark";
  try { t = localStorage.getItem("aurora_os_theme") || "dark"; } catch (e) {}
  document.documentElement.setAttribute("data-theme", t === "light" ? "light" : "dark");
})();
