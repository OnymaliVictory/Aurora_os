// ============================================================
// Aurora background — horizontal ribbons of light drifting slowly across
// the sky, like real aurora borealis. Each band undulates and glows, with
// a slow overall color cycle, twinkling stars, and gentle cursor parallax.
// ============================================================
(function(){
  const canvas=document.getElementById('aurora-canvas');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
  let w,h,t=0,dpr=Math.min(window.devicePixelRatio||1,2);
  let mx=0.5,my=0.35,tmx=0.5,tmy=0.35; // parallax target / eased position

  // Each band is a horizontal ribbon of light: y = its vertical position
  // (as a fraction of screen height), amp = how much it undulates up and
  // down, thickness = how tall the glow is. Speeds are deliberately slow —
  // real aurora drifts, it doesn't dart around.
  const bands=[
    {hue:158, y:.16, amp:.05,  speed:.000045, thickness:.16, phase:0.0},
    {hue:190, y:.30, amp:.04,  speed:.000035, thickness:.13, phase:1.4},
    {hue:265, y:.46, amp:.06,  speed:.000050, thickness:.19, phase:2.6},
    {hue:320, y:.60, amp:.045, speed:.000038, thickness:.14, phase:3.9},
    {hue:172, y:.74, amp:.04,  speed:.000055, thickness:.11, phase:5.1},
    {hue:210, y:.40, amp:.055, speed:.000030, thickness:.17, phase:0.8},
  ];

  const stars=[];
  function initStars(){
    stars.length=0;
    const count = w < 640 ? 110 : 190;
    for(let i=0;i<count;i++) stars.push({
      x:Math.random()*w, y:Math.random()*h*.8,
      r:Math.random()*1.3+.15, base:.12+Math.random()*.6,
      tw:Math.random()*Math.PI*2, sp:.006+Math.random()*.016
    });
  }
  function resize(){
    w=window.innerWidth; h=window.innerHeight;
    canvas.width=w*dpr; canvas.height=h*dpr;
    canvas.style.width=w+'px'; canvas.style.height=h+'px';
    ctx.setTransform(dpr,0,0,dpr,0,0);
    initStars();
  }
  window.addEventListener('resize',resize); resize();
  window.addEventListener('pointermove', e=>{
    tmx = e.clientX / w; tmy = e.clientY / h;
  }, { passive:true });

  function hsla(h,s,l,a){ return `hsla(${h},${s}%,${l}%,${a})`; }

  function draw(){
    t+=1;
    mx += (tmx-mx)*0.02; my += (tmy-my)*0.02;
    ctx.clearRect(0,0,w,h);

    const isLight=document.documentElement.getAttribute('data-theme')==='light';
    const starRGB=isLight?'15,23,42':'255,255,255';
    const glowMul=isLight?0.45:1;
    const hueDrift = (t*0.004) % 360; // whole aurora slowly cycles hue over minutes

    // Stars first, behind the bands
    stars.forEach(s=>{
      s.tw+=s.sp;
      const alpha=s.base*(0.5+0.5*Math.sin(s.tw))*(isLight?0.45:1);
      const px = (mx-0.5)*8, py=(my-0.5)*8;
      ctx.beginPath(); ctx.arc(s.x+px,s.y+py,s.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(${starRGB},${alpha})`; ctx.fill();
    });

    ctx.globalCompositeOperation = isLight ? 'source-over' : 'lighter';

    bands.forEach((band,bi)=>{
      const steps=56;
      const parallax = (my-0.5) * 22 * (1+bi*0.12);
      const baseY = band.y*h + parallax;
      const hue = (band.hue + hueDrift) % 360;
      const tv = t*band.speed*1000;

      // Build a gently undulating horizontal spine across the whole width
      const pts=[];
      for(let i=0;i<=steps;i++){
        const nx = i/steps;
        const wave = Math.sin(nx*3.4 + tv + band.phase) * band.amp
                   + Math.sin(nx*1.6 - tv*.6 + band.phase*1.7) * band.amp * .45;
        const x = nx*w;
        const y = baseY + wave*h;
        pts.push({ x, y });
      }

      const bandH = band.thickness * h * (0.75 + 0.25*Math.sin(tv*.5+band.phase));

      // Soft wide glow pass
      const grad=ctx.createLinearGradient(0,baseY-bandH,0,baseY+bandH);
      grad.addColorStop(0, hsla(hue,90,60,0));
      grad.addColorStop(.5, hsla(hue,90,62,.16*glowMul));
      grad.addColorStop(1, hsla(hue,90,60,0));
      ctx.beginPath();
      ctx.moveTo(pts[0].x,pts[0].y-bandH*.5);
      for(let i=1;i<pts.length;i++){const p=pts[i-1],q=pts[i];ctx.quadraticCurveTo(p.x,p.y-bandH*.5,(p.x+q.x)/2,(p.y+q.y)/2-bandH*.5)}
      for(let i=pts.length-1;i>=0;i--){const p=pts[i];ctx.lineTo(p.x,p.y+bandH*.5)}
      ctx.closePath(); ctx.fillStyle=grad; ctx.fill();

      // Brighter inner core streak
      const core=ctx.createLinearGradient(0,baseY-bandH*.2,0,baseY+bandH*.2);
      core.addColorStop(0, hsla(hue,95,70,0));
      core.addColorStop(.5, hsla(hue,95,75,.26*glowMul));
      core.addColorStop(1, hsla(hue,95,70,0));
      ctx.beginPath();
      ctx.moveTo(pts[0].x,pts[0].y);
      for(let i=1;i<pts.length;i++){const p=pts[i-1],q=pts[i];ctx.quadraticCurveTo(p.x,p.y,(p.x+q.x)/2,(p.y+q.y)/2)}
      ctx.strokeStyle=core; ctx.lineWidth=bandH*.32; ctx.lineCap='round'; ctx.stroke();
    });

    ctx.globalCompositeOperation='source-over';
    requestAnimationFrame(draw);
  }
  draw();
})();

(function(){
  const canvas=document.getElementById('shop-cover-canvas');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
  let w,h,t=0;
  function resize(){w=canvas.width=canvas.offsetWidth;h=canvas.height=canvas.offsetHeight}
  resize(); window.addEventListener('resize',resize);
  const blobs=[[0,255,179],[0,212,255],[168,85,247],[244,114,182],[0,180,220]];
  function draw(){
    t+=0.1; ctx.clearRect(0,0,w,h);
    blobs.forEach(([r,g,b],i)=>{
      const x=(Math.sin(t*.0004+i*1.7)*.4+.5)*w;
      const y=(Math.sin(t*.0003+i*2.3)*.35+.5)*h;
      const grad=ctx.createRadialGradient(x,y,0,x,y,w*.45);
      grad.addColorStop(0,`rgba(${r},${g},${b},.17)`);
      grad.addColorStop(1,`rgba(${r},${g},${b},0)`);
      ctx.beginPath(); ctx.arc(x,y,w*.45,0,Math.PI*2);
      ctx.fillStyle=grad; ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
})();