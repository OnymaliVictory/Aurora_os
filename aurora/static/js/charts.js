/* Tiny offline charts (no libraries): area/line, bars, donut. They follow the current theme colours. */
(function () {
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function setup(cv) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2), r = cv.getBoundingClientRect();
    cv.width = r.width * dpr; cv.height = r.height * dpr;
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { c, w: r.width, h: r.height };
  }
  function nice(max) { if (max <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(max))), f = max / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
  function axes(c, w, h, pad, maxV, fmt) {
    c.font = "11px Inter, sans-serif"; c.fillStyle = css("--faint"); c.strokeStyle = css("--line"); c.lineWidth = 1; c.textAlign = "right";
    for (let i = 0; i <= 4; i++) { const y = pad.t + (h - pad.t - pad.b) * (1 - i / 4); c.beginPath(); c.moveTo(pad.l, y); c.lineTo(w - pad.r, y); c.stroke(); c.fillText(fmt(maxV * i / 4), pad.l - 8, y + 4); }
  }
  const Charts = (window.Charts = {});
  function draw(cv, fn) { const render = () => fn(setup(cv)); render(); cv._r = render; }
  window.addEventListener("resize", () => document.querySelectorAll("canvas").forEach((c) => c._r && c._r()));
  window.addEventListener("themechange", () => setTimeout(() => document.querySelectorAll("canvas").forEach((c) => c._r && c._r()), 30));

  Charts.line = (cv, labels, values, o) => {
    o = o || {}; const fmt = o.fmt || ((v) => Math.round(v));
    draw(cv, ({ c, w, h }) => {
      const pad = { l: 54, r: 14, t: 12, b: 26 }, maxV = nice(Math.max(...values, 1) / 4) * 4, n = values.length;
      axes(c, w, h, pad, maxV, fmt);
      const X = (i) => pad.l + (n < 2 ? (w - pad.l - pad.r) / 2 : i * (w - pad.l - pad.r) / (n - 1)), Y = (v) => pad.t + (h - pad.t - pad.b) * (1 - v / maxV);
      const g = c.createLinearGradient(0, pad.t, 0, h - pad.b); g.addColorStop(0, css("--accent") + "66"); g.addColorStop(1, css("--accent") + "00");
      c.beginPath(); values.forEach((v, i) => (i ? c.lineTo(X(i), Y(v)) : c.moveTo(X(i), Y(v))));
      c.lineTo(X(n - 1), h - pad.b); c.lineTo(X(0), h - pad.b); c.closePath(); c.fillStyle = g; c.fill();
      const s = c.createLinearGradient(pad.l, 0, w, 0); s.addColorStop(0, css("--accent")); s.addColorStop(1, css("--accent-3"));
      c.beginPath(); values.forEach((v, i) => (i ? c.lineTo(X(i), Y(v)) : c.moveTo(X(i), Y(v)))); c.strokeStyle = s; c.lineWidth = 2.5; c.lineJoin = "round"; c.stroke();
      c.fillStyle = css("--accent"); values.forEach((v, i) => { if (n <= 31) { c.beginPath(); c.arc(X(i), Y(v), 3, 0, 7); c.fill(); } });
      c.fillStyle = css("--faint"); c.textAlign = "center"; const step = Math.ceil(n / 8);
      labels.forEach((l, i) => { if (i % step === 0 || (i === n - 1 && (n - 1) % step > step / 2)) c.fillText(l, X(i), h - 8); });
    });
  };
  Charts.bars = (cv, labels, values, o) => {
    o = o || {}; const fmt = o.fmt || ((v) => Math.round(v));
    draw(cv, ({ c, w, h }) => {
      const pad = { l: 54, r: 10, t: 12, b: 26 }, maxV = nice(Math.max(...values, 1) / 4) * 4, n = values.length, bw = (w - pad.l - pad.r) / n;
      axes(c, w, h, pad, maxV, fmt);
      const g = c.createLinearGradient(0, pad.t, 0, h - pad.b); g.addColorStop(0, css("--accent-2")); g.addColorStop(1, css("--accent"));
      values.forEach((v, i) => { const bh = (h - pad.t - pad.b) * v / maxV, x = pad.l + i * bw + bw * .18; c.fillStyle = g; c.beginPath(); c.roundRect ? c.roundRect(x, h - pad.b - bh, bw * .64, bh, 5) : c.rect(x, h - pad.b - bh, bw * .64, bh); c.fill(); });
      c.fillStyle = css("--faint"); c.textAlign = "center"; const step = Math.ceil(n / 12);
      labels.forEach((l, i) => { if (i % step === 0) c.fillText(l, pad.l + i * bw + bw / 2, h - 8); });
    });
  };
  Charts.donut = (cv, items, o) => {          // items: [{label, value, color}]
    o = o || {};
    draw(cv, ({ c, w, h }) => {
      const tot = items.reduce((a, b) => a + b.value, 0), cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 6, r = R * .64;
      if (!tot) { c.strokeStyle = css("--line-2"); c.lineWidth = R - r; c.beginPath(); c.arc(cx, cy, (R + r) / 2, 0, 7); c.stroke(); return; }
      let a0 = -Math.PI / 2;
      items.forEach((it) => { const a1 = a0 + (it.value / tot) * Math.PI * 2; c.beginPath(); c.arc(cx, cy, (R + r) / 2, a0, a1 - .02); c.strokeStyle = it.color; c.lineWidth = R - r; c.lineCap = "butt"; c.stroke(); a0 = a1; });
      if (o.center) { c.fillStyle = css("--text"); c.textAlign = "center"; c.font = "700 17px Syne, Inter"; c.fillText(o.center, cx, cy + 2); c.font = "11px Inter"; c.fillStyle = css("--muted"); c.fillText(o.sub || "", cx, cy + 18); }
    });
  };
  Charts.palette = () => [css("--accent"), css("--accent-2"), css("--accent-3"), css("--warn"), "#f472b6", "#fb923c", css("--bad"), "#94a3b8"];
})();
