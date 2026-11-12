// API endpoint configuration.
// The default /api works when the Mini App and API share the same HTTPS origin.
// For a separate API host, set <meta name="mini-app-api-url" content="https://YOUR-API-HOST/api"> in index.html.
const API_BASE = (
  window.__MINI_APP_API_URL__ ||
  document.querySelector('meta[name="mini-app-api-url"]')?.content ||
  "/api"
).replace(/\/+$/, "");

const tg = window.Telegram.WebApp;

let historyPage = 0;
let historyTotal = 0;
let boomPollTimer = null;

// Small celebratory burst for real wins (Boom / Number Game). Pure CSS
// animation, no external libraries -- pieces are removed after they
// finish falling so this never leaks DOM nodes on repeat wins.
function celebrateWin() {
  const layer = document.getElementById("confetti-layer");
  if (!layer) return;
  document.body.classList.remove("win-pulse");
  void document.body.offsetWidth;
  document.body.classList.add("win-pulse");
  setTimeout(() => document.body.classList.remove("win-pulse"), 1200);
  const pieces = "🪙🏆✨🟡";
  for (let i = 0; i < 24; i++) {
    const el = document.createElement("span");
    el.className = "confetti-piece";
    el.textContent = pieces[Math.floor(Math.random() * pieces.length)];
    el.style.left = Math.random() * 100 + "%";
    el.style.animationDelay = (Math.random() * 0.3) + "s";
    el.style.fontSize = (14 + Math.random() * 12) + "px";
    layer.appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }
}

// ------------------------------------------------------------
// 3D WIN CELEBRATION (Three.js coin burst)
//
// Purely celebratory -- plays once per real win, then the WebGL
// context is fully torn down. This is NOT a retention/urgency
// mechanic: no popups, no countdowns, nothing blocks the user or
// tries to keep them from leaving. It's a visual reward for a win
// that already happened, same spirit as the 2D confetti it plays
// alongside.
//
// Three.js is loaded lazily (only the first time a win happens) so
// pages that never see a win never pay for it. The renderer is
// destroyed right after the burst finishes -- a WebGL context left
// running in the background is a real battery/perf cost on the
// phones this Mini App mostly runs on.
// ------------------------------------------------------------

let _threeLoadPromise = null;
function loadThreeJs() {
  if (window.THREE) return Promise.resolve();
  if (_threeLoadPromise) return _threeLoadPromise;
  _threeLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
    script.integrity = "sha384-CI3ELBVUz9XQO+97x6nwMDPosPR5XvsxW2ua7N1Xeygeh1IxtgqtCkGfQY9WWdHu";
    script.crossOrigin = "anonymous";
    script.referrerPolicy = "no-referrer";
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
  return _threeLoadPromise;
}

function celebrateWin3DFallback() {
  const layer = document.getElementById("win3d-layer");
  if (!layer) return;
  layer.querySelectorAll(".fallback-3d-piece").forEach(el => el.remove());
  for (let i = 0; i < 18; i++) {
    const el = document.createElement("span");
    el.className = "fallback-3d-piece";
    el.textContent = i % 3 === 0 ? "🏆" : (i % 3 === 1 ? "🪙" : "✨");
    el.style.left = (10 + Math.random() * 80) + "%";
    el.style.setProperty("--x", ((Math.random() - .5) * 180) + "px");
    el.style.setProperty("--r", ((Math.random() - .5) * 720) + "deg");
    el.style.animationDelay = (Math.random() * .18) + "s";
    layer.appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }
}

async function celebrateWin3D() {
  // Respect the same reduced-motion preference the CSS animations
  // already honor -- some people get genuinely uncomfortable with
  // this kind of motion, not just "don't like flashy UI".
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const layer = document.getElementById("win3d-layer");
  if (!layer) return;

  try {
    await loadThreeJs();
  } catch (e) {
    // CDN/WebGL unavailable: keep the same 3D-feel with a zero-dependency
    // CSS 3D fallback so the win animation still works offline.
    celebrateWin3DFallback();
    return;
  }

  const THREE = window.THREE;
  const width = window.innerWidth, height = window.innerHeight;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 100);
  camera.position.z = 12;

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  layer.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const point = new THREE.PointLight(0xffd27a, 1.2);
  point.position.set(3, 5, 6);
  scene.add(point);

  // Coins: flattened gold cylinders, matching the app's own gold
  // theme (--gold-soft / --gold-deep) rather than a generic effect.
  const coinGeo = new THREE.CylinderGeometry(0.5, 0.5, 0.12, 24);
  const coinMat = new THREE.MeshStandardMaterial({ color: 0xe0a941, metalness: 0.7, roughness: 0.25 });

  const coins = [];
  const COIN_COUNT = 14;
  for (let i = 0; i < COIN_COUNT; i++) {
    const coin = new THREE.Mesh(coinGeo, coinMat);
    coin.position.set((Math.random() - 0.5) * 6, -6 - Math.random() * 2, (Math.random() - 0.5) * 3);
    coin.rotation.x = Math.random() * Math.PI;
    coin.userData.vy = 0.12 + Math.random() * 0.09;
    coin.userData.spin = 0.08 + Math.random() * 0.12;
    coin.userData.drift = (Math.random() - 0.5) * 0.03;
    scene.add(coin);
    coins.push(coin);
  }

  const start = performance.now();
  const DURATION = 1800;
  let rafId;

  function teardown() {
    cancelAnimationFrame(rafId);
    coins.forEach((c) => { c.geometry.dispose && c.geometry.dispose(); });
    coinGeo.dispose();
    coinMat.dispose();
    renderer.dispose();
    if (layer.contains(renderer.domElement)) layer.removeChild(renderer.domElement);
  }

  function tick(now) {
    const elapsed = now - start;
    for (const coin of coins) {
      coin.position.y += coin.userData.vy;
      coin.position.x += coin.userData.drift;
      coin.rotation.x += coin.userData.spin;
      coin.rotation.y += coin.userData.spin * 0.6;
    }
    renderer.render(scene, camera);
    if (elapsed < DURATION) {
      rafId = requestAnimationFrame(tick);
    } else {
      teardown();
    }
  }
  rafId = requestAnimationFrame(tick);
}


// ------------------------------------------------------------
// TRUE WEBGL / THREE.JS GAME BOARDS
// Every cabinet game gets an actual WebGL renderer and game-specific
// 3D primitives. The server remains authoritative; this layer is only
// presentation. If WebGL/CDN is unavailable, the native Canvas scene
// below remains the safe visual fallback.
// ------------------------------------------------------------
const webglScenes = new Map();
function disposeThreeScene(key){
  const x=webglScenes.get(key); if(!x) return;
  try{cancelAnimationFrame(x.raf); x.renderer.dispose(); x.host.querySelectorAll('canvas.webgl-game-canvas').forEach(c=>c.remove());}catch(e){}
  webglScenes.delete(key);
}
function addMat(THREE,color,metal=0.25,rough=.55){return new THREE.MeshStandardMaterial({color,metalness:metal,roughness:rough});}
function makeGameObject(THREE,key,outcome){
  const root=new THREE.Group();
  const mat=addMat(THREE,0xd8a83e,.65,.28), dark=addMat(THREE,0x182432,.2,.65), white=addMat(THREE,0xe9edf2,.1,.4), red=addMat(THREE,0xd83b52,.25,.45), cyan=addMat(THREE,0x39d5ff,.5,.25), green=addMat(THREE,0x23c77a,.25,.4);
  if(key==='dice') root.add(new THREE.Mesh(new THREE.BoxGeometry(2.8,2.8,2.8),white));
  else if(key==='slot'){for(let i=0;i<3;i++){const m=new THREE.Mesh(new THREE.CylinderGeometry(.8,.8,1.9,32),white);m.rotation.z=Math.PI/2;m.position.x=(i-1)*2.05;root.add(m);}}
  else if(key==='wheel'){const m=new THREE.Mesh(new THREE.CylinderGeometry(2.6,2.6,.42,48),mat);m.rotation.x=Math.PI/2;root.add(m);const hub=new THREE.Mesh(new THREE.CylinderGeometry(.45,.45,.55,32),white);hub.rotation.x=Math.PI/2;root.add(hub);}
  else if(key==='keno'){for(let i=0;i<20;i++){const m=new THREE.Mesh(new THREE.BoxGeometry(.55,.18,.55),i%5===0?mat:dark);m.position.set((i%5-2)*.78,.05,(Math.floor(i/5)-1.5)*.78);root.add(m);}}
  else if(key==='chicken'||key==='rabbit'){for(let i=0;i<12;i++){const b=new THREE.Mesh(new THREE.BoxGeometry(.65,.22,.65),i<Number(outcome?.steps||3)?green:dark);b.position.set((i-5.5)*.72,0,0);root.add(b);}const body=new THREE.Mesh(new THREE.SphereGeometry(.48,24,18),mat);body.position.y=.72;root.add(body);}
  else if(key==='aviator'||key==='jet'){const body=new THREE.Mesh(new THREE.ConeGeometry(.55,2.4,24),cyan);body.rotation.z=-Math.PI/2;root.add(body);const wing=new THREE.Mesh(new THREE.BoxGeometry(1.3,.12,3.0),mat);wing.position.z=.0;root.add(wing);}
  else if(key==='plinko'){for(let r=0;r<7;r++)for(let c=0;c<=r;c++){const peg=new THREE.Mesh(new THREE.SphereGeometry(.09,12,8),mat);peg.position.set((c-r/2)*.62,(3-r*.62),0);root.add(peg);}const ball=new THREE.Mesh(new THREE.SphereGeometry(.2,20,16),red);ball.name='plinkoBall';ball.position.y=3.8;root.add(ball);}
  else if(key==='mines'){for(let i=0;i<25;i++){const b=new THREE.Mesh(new THREE.BoxGeometry(.52,.18,.52),dark);b.position.set((i%5-2)*.66,.05,(Math.floor(i/5)-2)*.66);b.name=`mine-${i+1}`;root.add(b);}}
  else if(key==='fish'){for(let i=0;i<6;i++){const f=new THREE.Mesh(new THREE.SphereGeometry(.3+.06*(i%3),16,12),i%2?cyan:mat);f.position.set((i-2.5)*.9,.2+(i%2)*.35,(i%3-.9)*.5);root.add(f);}}
  else if(key==='card'){const card=new THREE.Mesh(new THREE.BoxGeometry(1.9,.12,2.8),white);card.rotation.y=.18;root.add(card);}
  else if(key==='boom'){for(let i=0;i<9;i++){const b=new THREE.Mesh(new THREE.BoxGeometry(.7,.22,.7),i%3===0?red:dark);b.position.set((i%3-1)*.9,.05,(Math.floor(i/3)-1)*.9);b.name=`boom-box-${i+1}`;root.add(b);}}
  else if(key==='number'){for(let i=0;i<15;i++){const b=new THREE.Mesh(new THREE.BoxGeometry(.48,.18,.48),i===0?mat:dark);b.position.set((i%5-2)*.65,.05,(Math.floor(i/5)-1)*.65);b.name=`number-${i+1}`;root.add(b);}}
  return root;
}
async function renderThreeGameScene(key,outcome={},phase='idle'){
  if(!document.getElementById(`${key}-scene`)) return;
  try{await loadThreeJs();}catch(e){return;}
  if(!window.THREE) return;
  const THREE=window.THREE, host=document.getElementById(`${key}-scene`); let old=webglScenes.get(key);
  if(old){ old.outcome=outcome; old.phase=phase; return; }
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,preserveDrawingBuffer:false}); renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.6)); renderer.setClearColor(0x000000,0);
  renderer.domElement.className='webgl-game-canvas'; renderer.domElement.setAttribute('aria-label',`${key} true WebGL game board`); host.insertBefore(renderer.domElement,host.firstChild); host.classList.add('has-webgl');
  const scene=new THREE.Scene(); const camera=new THREE.PerspectiveCamera(42,1,.1,100); camera.position.set(0,2.2,9); camera.lookAt(0,.4,0);
  scene.add(new THREE.AmbientLight(0xffffff,.72)); const light=new THREE.DirectionalLight(0xffd66b,1.15); light.position.set(3,6,5); scene.add(light);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(13,9),new THREE.MeshStandardMaterial({color:0x08131d,metalness:.1,roughness:.9,transparent:true,opacity:.45})); floor.rotation.x=-Math.PI/2; floor.position.y=-.35; scene.add(floor);
  const root=makeGameObject(THREE,key,outcome); scene.add(root);
  const state={renderer,scene,camera,root,host,raf:0,outcome,phase}; webglScenes.set(key,state);
  const resize=()=>{const r=host.getBoundingClientRect();const w=Math.max(280,r.width),h=Math.max(220,r.height);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}; resize();
  const tick=(now)=>{if(webglScenes.get(key)!==state)return; const t=now*.001; root.rotation.y=.12*Math.sin(t*.7); root.rotation.x=.04*Math.sin(t*.9);
    if(key==='plinko'){const b=root.getObjectByName('plinkoBall'); if(b){const p=(t%1.8)/1.8;b.position.y=3.7-p*6.0;b.position.x=Math.sin(p*12)*.6;}}
    if(key==='aviator'||key==='jet') root.position.y=.35*Math.sin(t*1.6);
    if(key==='wheel') root.rotation.z=t*.8;
    if(key==='slot') root.children.forEach((m,i)=>{m.rotation.x=t*(1.5+i*.25);});
    if(key==='fish') root.children.forEach((m,i)=>{m.position.x += Math.sin(t*1.2+i)*.0015;});
    const status=host.querySelector('.scene-status'), mult=host.querySelector('.scene-multiplier'); if(status){status.textContent=state.phase==='playing'?'LIVE':state.phase==='win'?'WIN':state.phase==='lose'?'RESULT':'READY';} if(mult){mult.textContent=state.outcome?.live_multiplier?`${Number(state.outcome.live_multiplier).toFixed(2)}×`:state.outcome?.multiplier!==undefined?`${state.outcome.multiplier}×`:'3D';}
    renderer.render(scene,camera); state.raf=requestAnimationFrame(tick);}; state.raf=requestAnimationFrame(tick);
}

function haptic(type) {
  // Best-effort only -- older Telegram clients / desktop don't support
  // HapticFeedback, so this must never throw and break the real action.
  try {
    if (type === "success") tg.HapticFeedback.notificationOccurred("success");
    else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
    else tg.HapticFeedback.impactOccurred("light");
  } catch (e) { /* ignore */ }
}

// Tiny local sound engine. It uses no remote assets and is best-effort only.
let gameAudioCtx = null;
function gameSound(type="tap") {
  try {
    if (!gameAudioCtx) gameAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (gameAudioCtx.state === "suspended") gameAudioCtx.resume();
    const now = gameAudioCtx.currentTime;
    const o = gameAudioCtx.createOscillator(), g = gameAudioCtx.createGain();
    const freq = type === "win" ? 660 : type === "lose" ? 180 : type === "round" ? 420 : 280;
    o.type = type === "win" ? "triangle" : "sine"; o.frequency.setValueAtTime(freq, now);
    o.frequency.exponentialRampToValueAtTime(type === "win" ? freq*1.35 : freq*.78, now+.16);
    g.gain.setValueAtTime(.0001, now); g.gain.exponentialRampToValueAtTime(.045, now+.015); g.gain.exponentialRampToValueAtTime(.0001, now+.18);
    o.connect(g).connect(gameAudioCtx.destination); o.start(now); o.stop(now+.2);
  } catch(e) {}
}

function applyTelegramTheme() {
  const root = document.documentElement;
  const p = tg.themeParams || {};
  const map = {
    "--tg-theme-bg-color": p.bg_color,
    "--tg-theme-text-color": p.text_color,
    "--tg-theme-secondary-bg-color": p.secondary_bg_color,
  };
  for (const [k, v] of Object.entries(map)) {
    if (v) root.style.setProperty(k, v);
  }
}

let adminPinToken = null; // in-memory only, never persisted -- cleared on page reload by design

// Escapes any string that came from user-controlled data (a Telegram
// first_name/username, a marketplace listing title, a review/report
// comment, an admin note, etc.) before it's inserted via innerHTML.
// Without this, a user who sets their Telegram name/username to
// contain HTML could run script in the browser of anyone who views
// it -- including an admin viewing user search, escrow, or report
// lists, which makes this the single highest-value fix in the app:
// it's the one path that can compromise the admin panel itself.
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Shown whenever the server answers 428 terms_not_accepted (e.g. the user
// passed the gate on an older version, or the server never recorded it).
// Re-asks the 18+ question, records it server-side, then resolves so the
// original request can be retried automatically.
function promptAgeGateAgain() {
  return new Promise((resolve, reject) => {
    const overlay = document.getElementById("age-gate-overlay");
    const yes = document.getElementById("age-gate-confirm");
    const no = document.getElementById("age-gate-decline");
    overlay.style.display = "flex";
    overlay.style.zIndex = "99999";
    const yes2 = yes.cloneNode(true); yes.parentNode.replaceChild(yes2, yes);
    const no2 = no.cloneNode(true); no.parentNode.replaceChild(no2, no);
    yes2.disabled = false;
    yes2.addEventListener("click", async () => {
      yes2.disabled = true;
      try {
        await apiFetch("/accept-terms", { method: "POST", _retried: true });
        try { localStorage.setItem("kdm_age_confirmed_v2", "1"); } catch (_) {}
        overlay.style.display = "none";
        resolve();
      } catch (e) {
        yes2.disabled = false;
        yes2.textContent = "❌ ማረጋገጫ አልተመዘገበም — እንደገና ይሞክሩ";
      }
    });
    no2.addEventListener("click", () => {
      overlay.style.display = "none";
      reject(new Error("18+ confirmation declined"));
    });
  });
}

async function apiFetch(path, { method = "GET", json = null, formData = null, idempotencyKey = null, _retried = false } = {}) {
  const headers = {
    // This is the ONLY thing that proves a request came from a real
    // Telegram user -- the backend re-validates it with the bot token
    // on every single call. Never trust a user_id sent any other way
    // (e.g. a URL query param), it's trivially spoofable.
    "X-Telegram-Init-Data": tg.initData,
  };
  // NOTE: this must catch any admin sub-path, not just ones directly
  // under /admin/ -- e.g. /marketplace/admin/resolve moves real money
  // and requires the PIN too, but doesn't start with "/admin/".
  if (path.includes("/admin/") && adminPinToken) {
    headers["X-Admin-Pin-Token"] = adminPinToken;
  }
  if (idempotencyKey) headers["X-Idempotency-Key"] = idempotencyKey;
  const opts = { method, headers };
  if (json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  } else if (formData) {
    opts.body = formData; // browser sets multipart boundary itself
  }

  const res = await fetch(API_BASE + path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 428 && body.error === "terms_not_accepted" && !_retried) {
      await promptAgeGateAgain();
      return apiFetch(path, { method, json, formData, idempotencyKey, _retried: true });
    }
    const serverMessage = String(body.message || body.error || "");
    if (res.status === 401 && /session too old|initData expired|reopen the Mini App/i.test(serverMessage)) {
      throw new Error("Session expired. እባክዎ Telegram Mini App-ን ዝጉና እንደገና ይክፈቱ።");
    }
    if (body.pin_required) {
      adminPinToken = null; // stale/expired -- force a fresh PIN prompt next time
      const err = new Error(body.error || "admin PIN required");
      err.pinRequired = true;
      throw err;
    }
    const err = new Error(body.message || body.error || `HTTP ${res.status}`);
    err.body = body; // lets callers inspect e.g. body.error === "self_excluded" or body.until
    throw err;
  }
  return body;
}

function showError(msg) {
  document.getElementById("loading").style.display = "none";
  document.getElementById("content").style.display = "none";
  const el = document.getElementById("error");
  el.style.display = "block";
  el.textContent = "❌ " + msg;
  const retry = document.createElement("button");
  retry.type = "button"; retry.textContent = "🔄 እንደገና ሞክር";
  retry.style.cssText = "display:block;margin:14px auto 0;padding:10px 18px;border-radius:10px;border:0;background:#1d6bff;color:#fff;font-weight:800";
  retry.addEventListener("click", () => location.reload());
  el.appendChild(retry);
}

// Renders a game/bet error into `el`. If the backend reported
// "insufficient balance", shows a distinct message with a button
// that jumps straight to the Wallet/Deposit page instead of a bare
// "❌ Error" -- the whole point being the user immediately knows
// *what* went wrong and *what to do about it*, rather than having to
// guess and navigate there themselves.
function renderActionError(el, message) {
  const isBalanceError = /insufficient balance/i.test(message || "");
  if (isBalanceError) {
    el.innerHTML = "";
    const span = document.createElement("span");
    span.textContent = "🔴 በቂ ቀሪ ሂሳብ የለዎትም — ";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "inline-deposit-btn";
    btn.textContent = "Deposit ያድርጉ";
    btn.addEventListener("click", () => goToPage("wallet"));
    el.appendChild(span);
    el.appendChild(btn);
  } else {
    el.textContent = "❌ " + message;
  }
}

let lastProfile = null;

// Animates the balance display from its previous value to the new
// one over ~500ms, instead of the number just jumping -- makes wins,
// losses, and deposits landing feel like something actually happened.
function animateBalance(from, to) {
  const el = document.getElementById("balance");
  const duration = 500;
  const start = performance.now();
  function step(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = from + (to - from) * eased;
    el.textContent = current.toFixed(2);
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = to.toFixed(2);
  }
  requestAnimationFrame(step);
}

async function refreshBalance() {
  const p = await apiFetch("/profile");
  const prevBalance = lastProfile ? lastProfile.balance : null;
  lastProfile = p;
  if (prevBalance !== null && p.balance !== prevBalance) {
    animateBalance(prevBalance, p.balance);
    const pill = document.getElementById("balance-pill");
    pill.classList.remove("pulse");
    void pill.offsetWidth; // restart animation if it's already mid-pulse
    pill.classList.add("pulse");
  } else {
    document.getElementById("balance").textContent = p.balance.toFixed(2);
  }

  // Keep the Profile page's own balance line in sync too -- it used
  // to only get set once at launch (in loadProfile), so it went
  // stale the moment any game, marketplace purchase, or withdrawal
  // changed the balance afterwards.
  const profileBalanceEl = document.getElementById("profile-balance");
  if (profileBalanceEl) profileBalanceEl.textContent = `💰 ${p.balance.toFixed(2)} ብር`;

  const badge = document.getElementById("wallet-badge");
  if (badge) badge.style.display = p.has_pending ? "block" : "none";

  const bn = document.getElementById("withdraw-bonus-note");
  if (bn) {
    const lk = Number(p.bonus_locked || 0);
    bn.style.display = lk > 0 ? "block" : "none";
    if (lk > 0) bn.textContent = `🎁 Bonus ${lk.toFixed(2)} ብር ለመጫወት ብቻ ነው። ማውጣት የሚችሉት: ${Number(p.withdrawable || 0).toFixed(2)} ብር`;
  }

  return p;
}

async function loadProfile() {
  const p = await refreshBalance();
  document.getElementById("greeting").textContent = `ሰላም ${p.first_name || "!"}`;
  document.getElementById("profile-name").textContent = `👤 ${p.first_name || ""} ${p.username ? "(@" + p.username + ")" : ""}`;
  document.getElementById("profile-id").textContent = `🆔 ${p.user_id}`;
  document.getElementById("profile-balance").textContent = `💰 ${p.balance.toFixed(2)} ብር`;

  const avatar = document.getElementById("profile-avatar");
  if (avatar) avatar.textContent = (p.first_name || "?").trim().charAt(0).toUpperCase();

  const adminBtn = document.getElementById("open-admin-panel");
  if (adminBtn) adminBtn.style.display = p.is_staff ? "block" : "none";

  maybeShowWelcome(p);
  return p;
}

// ------------------------------------------------------------
// ONE-TIME ONBOARDING WELCOME CARD
// ------------------------------------------------------------

function maybeShowWelcome(profile) {
  const KEY = "kdm_welcome_shown";
  let alreadyShown = false;
  try { alreadyShown = localStorage.getItem(KEY) === "1"; } catch (e) { /* ignore */ }
  if (alreadyShown) return;

  const overlay = document.getElementById("welcome-overlay");
  if (!overlay) return;
  document.getElementById("welcome-title").textContent =
    `እንኳን ደህና መጡ፣ ${profile.first_name || "ወዳጅ"}! ☕`;
  overlay.style.display = "flex";

  const close = () => {
    overlay.style.display = "none";
    try { localStorage.setItem(KEY, "1"); } catch (e) { /* ignore */ }
  };
  document.getElementById("welcome-close").addEventListener("click", close, { once: true });
}

// ------------------------------------------------------------
// RECENT BIG WINS TICKER (real data from /api/wins/recent)
// ------------------------------------------------------------

// Server win keys that are variants/aliases of a lobby game -> the lobby page that actually exists (a tap must never fail).
const WIN_GAME_ALIAS = { bomb: "boom", minesx: "mines", coin: "coinstreak", coinflip: "coinstreak", dice: "dice2", number_live: "number", auction: "marketplace",
  group_mines: "boom", aviator_live: "aviator", jet_live: "jet", rocket_live: "rocket", keno_live: "keno" };
function resolveWinGame(k) {
  k = String(k || "").toLowerCase();
  if (!k) return "";
  if (/^slot_\d+$/.test(k)) return window.kdmHasVariant && window.kdmHasVariant(k) ? k : "slot";   // the exact slot skin that was won on
  if (window.kdmHasVariant && window.kdmHasVariant(k)) return k;                                    // Crash / Rocket / High Flyer / Sky Masters / Power|Super|Insta Keno / Triple Gold Deluxe ...
  if (GAMES.some((g) => g.key === k)) return k;
  const a = WIN_GAME_ALIAS[k];
  return a && GAMES.some((g) => g.key === a) ? a : "";
}
let winsTickerSig = "";

async function loadWinsTicker() {
  const track = document.getElementById("wins-track-inner");
  if (!track) return;
  if (!track.children.length) track.innerHTML = `<div class="skeleton-line" style="width:140px;display:inline-block"></div>`;
  try {
    const data = await apiFetch("/wins/recent");
    if (!data.wins || !data.wins.length) {
      winsTickerSig = "";
      track.style.removeProperty("animation-duration");
      track.innerHTML = `<span class="wins-empty">🎯 እስካሁን ምንም ማሸነፍ የለም -- የመጀመሪያው እርስዎ ይሁኑ!</span>`;
      return;
    }
    const sig = JSON.stringify(data.wins.map((w) => [w.name, w.game, w.amount, w.created_at]));
    if (sig === winsTickerSig && track.querySelector(".win-chip")) return;   // unchanged -> no re-render, no animation jump
    winsTickerSig = sig;
    const hue = (s) => { let x = 0; for (const c of String(s || "x")) x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
    const fmtBr = (n) => "Br" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
    const chip = (w) => {
      const gk = resolveWinGame(w.game);                       // lobby page this win opens (may be "" -> opens the games list)
      const gm = GAMES.find((g) => g.key === gk) || GAMES.find((g) => g.key === w.game);
      const gname = w.game_name || (gm && gm.name) || "";
      const cover = window.kdmCover ? (window.kdmCover(gk || w.game, w.icon || (gm && gm.icon)) || window.kdmCover(w.game, w.icon)) : null;
      const icon = w.icon || (gm && gm.icon) || "🎉";
      const mult = Number(w.multiplier) > 1 ? `<em class="win-x">×${Number(w.multiplier).toLocaleString(undefined, { maximumFractionDigits: 2 })}</em>` : "";
      return `
      <button type="button" class="win-chip${cover ? " has-cover" : ""}" data-game="${escapeHtml(gk)}" style="--wh:${hue(w.game || w.icon)}" title="${escapeHtml((gname ? gname + " · " : "") + w.name)}">
        <div class="win-thumb" aria-hidden="true"${cover ? ` style="background-image:url('${cover}')"` : ""}>${cover ? "" : escapeHtml(icon)}</div>
        <div class="win-game">${escapeHtml(gname || "Win")}</div>
        <div class="win-chip-title">${escapeHtml(w.name)}</div>
        <div class="win-amt-row"><span class="amt">${fmtBr(w.amount)}</span>${mult}</div>
      </button>`;
    };
    // The CSS animation moves the track by exactly -50%, so the content is two identical halves, and each half must be wider than the
    // screen (otherwise the right side runs empty). Spacing is margin-right on every chip (not flex gap + padding) so -50% lands exactly
    // on the start of the second half = a seamless loop with no jump.
    const n = data.wins.length, UNIT = 146;                    // ~chip width + spacing
    const vw = Math.max((track.parentElement && track.parentElement.clientWidth) || 0, window.innerWidth || 0, 360);
    const rep = Math.max(1, Math.ceil((vw * 1.3) / (n * UNIT)));
    const half = data.wins.map(chip).join("").repeat(rep);
    track.innerHTML = half + half;
    track.style.setProperty("gap", "0", "important");
    track.style.setProperty("padding", "0", "important");
    track.style.setProperty("animation-duration", Math.max(18, Math.round((n * rep * UNIT) / 48)) + "s", "important");
    track.querySelectorAll(".win-chip").forEach((el) => el.style.setProperty("margin-right", "10px", "important"));
    if (!track.dataset.tap) {
      track.dataset.tap = "1";
      track.addEventListener("click", (e) => {
        const c = e.target.closest(".win-chip"); if (!c) return;
        try { goToPage(c.dataset.game || "lobby"); haptic("success"); } catch (_) { try { goToPage("lobby"); } catch (__) {} }
      });
    }
  } catch (e) {
    // Non-critical -- keep whatever is already shown; only clear the loading skeleton.
    if (track.querySelector(".skeleton-line")) track.innerHTML = "";
  }
}

// ------------------------------------------------------------
// LOBBY / GAME GRID
// ------------------------------------------------------------

const GAMES = [
  { key: "boom", icon: "💣", name: "Boom Game", color: "#c1502e", color2: "#7a2c17", badge: "🔥 HOT", cats: ["hot", "popular"] },
  { key: "number", icon: "🔢", name: "Number Game", color: "#2f9e6b", color2: "#175c3e", badge: "⚡ FAST", cats: ["fast"] },
  { key: "aviator", icon: "✈️", name: "Aviator", color: "#06b6d4", color2: "#164e63", badge: "🚀", cats: ["hot", "popular"] },
  { key: "keno", icon: "🎯", name: "Keno", color: "#14b8a6", color2: "#115e59", badge: "⚡ FAST", cats: ["fast", "popular"] },
  { key: "mines", icon: "💣", name: "Mines", color: "#8b5cf6", color2: "#4c1d95", badge: "🔥 HOT", cats: ["hot"] },
  { key: "buffalo", icon: "🦬", name: "Buffalo Plains", color: "#ea580c", color2: "#3b1a07", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "aztec", icon: "🗿", name: "Aztec Gold", color: "#0f766e", color2: "#3b2a07", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "flame", icon: "🔥", name: "Flame Classics", color: "#f97316", color2: "#7c1d06", badge: "🔥 HOT", cats: ["hot", "popular"] },
  { key: "triplegold", icon: "🔔", name: "Triple Gold", color: "#f59e0b", color2: "#7c2d12", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "dice2", icon: "🎲", name: "Dice", color: "#3b82f6", color2: "#1e3a8a", badge: "⚡ FAST", cats: ["fast", "popular"] },
  { key: "plinko", icon: "🟣", name: "Plinko", color: "#a855f7", color2: "#581c87", badge: "NEW", cats: ["new", "popular"] },
  { key: "jet", icon: "🚀", name: "Jet", color: "#f97316", color2: "#7c2d12", badge: "🔥 HOT", cats: ["hot"] },
  { key: "roulette", icon: "🎡", name: "Roulette", color: "#16a34a", color2: "#052e16", badge: "🆕 NEW", cats: ["hot", "new", "popular"] },
  { key: "bingo", icon: "🎱", name: "Bingo", color: "#7c3aed", color2: "#2e1065", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "fastkeno", icon: "⚡", name: "Fast Keno", color: "#0ea5e9", color2: "#082f49", badge: "🆕 NEW", cats: ["hot", "new"] },
  { key: "penaltystreak", icon: "⚽", name: "Penalty Streak", color: "#16a34a", color2: "#052e16", badge: "🆕 NEW", cats: ["hot", "new", "popular"] },
  { key: "chicken2", icon: "🐔", name: "Chicken Road 2", color: "#1e3a8a", color2: "#0b1226", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "tower", icon: "💣", name: "Boom Ladder", color: "#7c3aed", color2: "#1e1b4b", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "roast", icon: "🔥", name: "Chicken Roast", color: "#f97316", color2: "#7c2d12", badge: "🆕 NEW", cats: ["hot", "new"] },
  { key: "rabbit", icon: "🐇", name: "Rabbit Road", color: "#22c55e", color2: "#14532d", badge: "🆕 NEW", cats: ["hot", "new"] },
  { key: "chicken", icon: "🐔", name: "Chicken Road", color: "#ef4444", color2: "#7f1d1d", badge: "🆕 NEW", cats: ["hot", "new", "popular"] },
  { key: "fish", icon: "🐟", name: "Fish", color: "#0ea5e9", color2: "#0c4a6e", badge: "NEW", cats: ["new"] },
  { key: "slot", icon: "🎰", name: "777 Slot", color: "#d946ef", color2: "#701a75", badge: "🔥 HOT", cats: ["hot", "popular"] },
  { key: "blackjack", icon: "🃏", name: "Blackjack", color: "#166534", color2: "#052e16", badge: "🆕 NEW", cats: ["hot", "new", "popular"] },
  { key: "dragontiger", icon: "🐉", name: "Dragon Tiger", color: "#dc2626", color2: "#450a0a", badge: "🆕 NEW", cats: ["hot", "new", "popular", "fast"] },
  { key: "andarbahar", icon: "🃏", name: "Andar Bahar", color: "#0d9488", color2: "#042f2e", badge: "🆕 NEW", cats: ["new", "popular"] },
  { key: "baccarat", icon: "🎴", name: "Baccarat", color: "#9f1239", color2: "#2a0710", badge: "🆕 NEW", cats: ["hot", "new", "popular"] },
  { key: "coinstreak", icon: "🪙", name: "Coin Flip", color: "#eab308", color2: "#713f12", badge: "NEW", cats: ["new", "fast", "popular"] },
  { key: "penalty", icon: "⚽", name: "Penalty Shootout", color: "#16a34a", color2: "#14532d", badge: "NEW", cats: ["new", "fast"] },
  { key: "card", icon: "🃏", name: "Card Table", color: "#64748b", color2: "#1e293b", badge: "NEW", cats: ["new"] },
  { key: "wheel", icon: "🎡", name: "Lucky Wheel", color: "#f59e0b", color2: "#92400e", badge: "🎯", cats: ["hot"] },
  { key: "sports", icon: "⚽", name: "Sports Betting", color: "#e0a941", color2: "#8a611f", badge: "", cats: ["hot", "fast"] },
  { key: "marketplace", icon: "🛍️", name: "Marketplace", color: "#6b4fa0", color2: "#3a2a5c", badge: "🎓 NEW", cats: ["hot", "new"] },
];

const ADDED_GAME_INFO = {
  dice: { title: "🎲 Dice", help: "1–6 ቁጥር ይምረጡ።" },
  buffalo: { title: "🦬 Buffalo Plains", help: "243 ways -- ተመሳሳይ ምልክት ከግራ በተከታታይ ሪሎች (ቢያንስ 3) ሲታይ ይከፍላል። 3+ 🪙 Stampede Bonus (ነጻ ዙሮች) ይጀምራል።" },
  aztec: { title: "🗿 Aztec Gold", help: "5 መስመሮች (3 ረድፍ + 2 ሰያፍ) -- መስመር ሦስት ተመሳሳይ ምልክት ሲይዝ ይከፍላል፤ ድምሩ ይከፈላል።" },
  flame: { title: "🔥 Flame Classics", help: "ሦስት ሪሎች ይዞራሉ -- መስመሩ ሦስት ተመሳሳይ ምልክት ወይም ሁለት 🍒 ሲይዝ ይከፍላል። አንዳንዴ በነጻ Hot Respin ይመጣል።" },
  triplegold: { title: "🔔 Triple Gold", help: "ሦስት ሪሎች ይዞራሉ -- መካከለኛው መስመር ሦስት ተመሳሳይ ምልክት ወይም ሁለት 🍒 ሲይዝ ይከፍላል።" },
  dice2: { title: "🎲 Dice", help: "ሁለት ዳይስ ይጣላሉ -- ድምሩ ከመረጡት ቁጥር በታች (Under)፣ እኩል (Exact) ወይም በላይ (Over) ይሆናል?" },
  coinstreak: { title: "🪙 Coin Flip", help: "Heads ወይም Tails ይምረጡ እና Flip ይጫኑ -- ተከታታይ ድል ሽልማቱን ያሳድጋል፣ በፈለጉት ጊዜ 💰 Cash Out ያድርጉ።" },
  slot: { title: "🎰 777 Slot", help: "3 reels ይዞራሉ።" },
  wheel: { title: "🎡 Lucky Wheel", help: "Multiplier ይጠብቁ።" },
  keno: { title: "🎯 Keno", help: "ከ1–80 ውስጥ 1 እስከ 10 ቁጥሮች ይምረጡ፣ 20 ኳሶች ይወጣሉ። ብዙ ሲመታ ብዙ ይከፈላል።" },
  roulette: { title: "🎡 Roulette", help: "አንድ ውርርድ ይምረጡ እና ያሽክርክሩ -- Red/Black፣ Odd/Even፣ Dozen፣ Column ወይም ቁጥር (36×)።" },
  bingo: { title: "🎱 Bingo", help: "ካርድ ይታደላል፣ 40 ኳሶች ይወጣሉ -- ብዙ መስመር ሲሞሉ ሽልማቱ ይጨምራል።" },
  fastkeno: { title: "⚡ Fast Keno", help: "4 ቁጥሮች ከ1–40 ይምረጡ፣ 10 ኳሶች ይወጣሉ። ፈጣን ዙር!" },
  penaltystreak: { title: "⚽ Penalty Streak", help: "ተከታታይ ምቶች -- እያንዳንዱ ግብ ሽልማቱን ያሳድጋል፤ በፈለጉት ጊዜ 💰 Cash Out ያድርጉ፣ ጠባቂው ካዳነ ይጠፋል።" },
  chicken2: { title: "🐔 Chicken Road 2", help: "ሌሊት ላይ 7 የትራፊክ መስመሮችን አንድ በአንድ ይሻገሩ -- እያንዳንዱ ደህና መሻገሪያ ሽልማቱን ይጨምራል፤ መኪና ከመታዎት ይጠፋል። ከማንኛውም ደህና መሻገሪያ በኋላ Cash Out ይችላሉ።" },
  tower: { title: "💣 Boom Ladder", help: "ደረጃ በደረጃ ይውጡ -- እያንዳንዱ ደረጃ ሽልማቱን ይጨምራል፤ ወጥመድ ከነኩ ይጠፋል፣ ከዚያ በፊት 💰 Cash Out ያድርጉ።" },
  roast: { title: "🔥 Chicken Roast", help: "ዶሮዋን ከእሳት አሻግሩ -- እያንዳንዱ ደረጃ ሽልማቱን ያሳድጋል፣ በፈለጉት ጊዜ Cash Out ያድርጉ።" },
  rabbit: { title: "🐇 Rabbit Road", help: "አጭር እና አደገኛ ትራክ (10 ዝላይ) -- ከፍተኛ ሽልማት፣ ከፍተኛ ሪስክ። በማንኛውም ዝላይ Cash Out ያድርጉ።" },
  chicken: { title: "🐔 Chicken Road", help: "መንገዱን ሌን በሌን ይሻገሩ -- በማንኛውም ደህንነቱ የተጠበቀ ሌን Cash Out ያድርጉ።" },
  aviator: { title: "✈️ Aviator", help: "ተነስቶ ከመከስከሱ በፊት CASH OUT ይጫኑ፣ ወይም Auto Cash-out (አማራጭ) ያስገቡ።" },
  plinko: { title: "🟣 Plinko", help: "Ball ይወርዳል እና multiplier ይሰጣል።" },
  mines: { title: "💣 Mines", help: "Mine ቁጥር እና cell ይምረጡ።" },
  jet: { title: "🚀 Jet", help: "ተነስቶ ከመከስከሱ በፊት CASH OUT ይጫኑ፣ ወይም Auto Cash-out (አማራጭ) ያስገቡ።" },
  fish: { title: "🐟 Fish", help: "Shot ይምረጡ።" },
  card: { title: "🃏 Card Table", help: "High ወይም Low ይምረጡ።" },
  blackjack: { title: "🃏 Blackjack", help: "ወደ 21 ይቅረቡ፣ ከ21 አይለፉ -- Dealer ን ይምቱ።" },
  dragontiger: { title: "🐉 Dragon Tiger", help: "Dragon፣ Tiger ወይም Tie ይምረጡ -- ትልቁ ካርድ ያሸንፋል።" },
  andarbahar: { title: "🃏 Andar Bahar", help: "አንደር ወይም ባሃር ይምረጡ -- የጆከሩን ቁጥር መጀመሪያ የሚያገኘው ወገን ያሸንፋል።" },
  baccarat: { title: "🎴 Baccarat", help: "Player፣ Banker ወይም Tie ይምረጡ -- ወደ 9 የቀረበው እጅ ያሸንፋል።" },
  coinflip: { title: "🪙 Coin Flip", help: "Heads ወይም Tails ይምረጡ -- ሳንቲሙ ሲቆም የመረጡት ከወጣ ያሸንፋሉ።" },
  penalty: { title: "⚽ Penalty Shootout", help: "ኳሱን የሚመቱበትን ጎን ይምረጡ -- ግብ ጠባቂው ከዘለለበት ጎን ካልሆነ ግብ ያስቆጥራሉ።" },
};

function ensureAddedGamePages() {
  const pages = document.getElementById("pages");
  for (const [key, info] of Object.entries(ADDED_GAME_INFO)) {
    if (document.getElementById("page-" + key)) continue;
    const section = document.createElement("section");
    section.id = "page-" + key; section.className = "page added-game-page";
    section.innerHTML = `
      <button class="back-btn" data-back="lobby">← Lobby</button>
      <h2>${info.title}</h2>
      <p class="fairness-note">${info.help}</p>
      <div id="${key}-scene" class="game-3d-scene" data-game="${key}"><canvas class="game-3d-canvas" aria-label="${escapeHtml(info.title)} gameplay animation"></canvas><div class="three-webgl-layer" aria-hidden="true"></div><div class="scene-vignette"></div><div class="scene-hud"><span class="scene-status">READY</span><span class="scene-multiplier">—</span></div></div>
      <div id="${key}-controls" class="game-controls"></div>
      <div id="${key}-result" class="game-result"></div>
      <button id="${key}-play" class="primary-game-btn">▶️ መጫወት</button>
      <button id="${key}-history-toggle" class="link-btn">📜 ታሪክ</button>
      <div id="${key}-history" style="display:none"></div>`;
    pages.insertBefore(section, document.getElementById("page-sports"));
    section.querySelector(".back-btn").addEventListener("click", () => goToPage("lobby"));
  }
}


/* ------------------------------------------------------------
   CABINET 3D GAME SCENES
   Native Canvas renderer: no external game provider and no CDN game engine.
   The server remains authoritative; these animations only visualize the
   returned server outcome and never decide a cash result.
------------------------------------------------------------ */
const sceneRaf = new Map();
const sceneState = new Map();

function sceneCanvas(key) {
  const c = document.querySelector(`#${key}-scene .game-3d-canvas`);
  if (!c) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = c.getBoundingClientRect();
  const w = Math.max(320, Math.floor(rect.width));
  const h = Math.max(230, Math.floor(rect.height));
  if (c.width !== Math.floor(w*dpr) || c.height !== Math.floor(h*dpr)) {
    c.width = Math.floor(w*dpr); c.height = Math.floor(h*dpr);
  }
  const ctx = c.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0);
  return {c,ctx,w,h};
}

function rr(ctx,x,y,w,h,r){ const q=Math.min(r,w/2,h/2); ctx.beginPath(); ctx.roundRect(x,y,w,h,q); }
function glowText(ctx,text,x,y,size,color,shadow=color){ctx.save();ctx.font=`900 ${size}px system-ui`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.shadowColor=shadow;ctx.shadowBlur=16;ctx.fillStyle=color;ctx.fillText(text,x,y);ctx.restore();}
function sceneBase(ctx,w,h,key,t){
  const palettes={dice:['#061426','#0e3560'],slot:['#16070c','#57131d'],wheel:['#171005','#6b4210'],keno:['#041c1d','#0d5d5b'],chicken:['#1b0907','#6e2413'],aviator:['#031725','#07527a'],plinko:['#16062a','#5b1b83'],mines:['#09070e','#39215c'],jet:['#170c03','#71310d'],fish:['#031726','#07547b'],rabbit:['#150617','#70204f'],card:['#06110b','#174f30'],coinflip:['#1a1204','#6b4a0c'],penalty:['#04140a','#14532d']};
  const [a,b]=palettes[key]||['#081012','#17333b'];
  const g=ctx.createRadialGradient(w*.5,h*.38,10,w*.5,h*.45,h*.8);g.addColorStop(0,b);g.addColorStop(1,a);ctx.fillStyle=g;ctx.fillRect(0,0,w,h);
  for(let i=0;i<18;i++){const x=(Math.sin(i*41.7+t*.00018)*.5+.5)*w,y=(Math.cos(i*17.1+t*.00012)*.5+.5)*h;ctx.fillStyle=`rgba(255,255,255,${.025+(i%3)*.01})`;ctx.beginPath();ctx.arc(x,y,1.5+(i%3),0,Math.PI*2);ctx.fill();}
  ctx.strokeStyle='rgba(255,214,83,.10)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(w*.08,h*.82);ctx.lineTo(w*.92,h*.82);ctx.stroke();
}
function drawDice(ctx,w,h,t,o){
  const roll=o?.roll||1, a=Math.sin(t*.012)*.18, size=Math.min(w,h)*.30, x=w/2-size/2+Math.sin(t*.009)*5, y=h*.36+Math.abs(Math.sin(t*.014))*10;
  ctx.save();ctx.translate(x+size/2,y+size/2);ctx.rotate(a);ctx.shadowColor='rgba(0,0,0,.65)';ctx.shadowBlur=25;ctx.shadowOffsetY=14;
  const g=ctx.createLinearGradient(-size/2,-size/2,size/2,size/2);g.addColorStop(0,'#fff');g.addColorStop(.5,'#dfe4ea');g.addColorStop(1,'#8f98a5');ctx.fillStyle=g;rr(ctx,-size/2,-size/2,size,size,size*.16);ctx.fill();
  ctx.shadowBlur=0;const pip=[[0,0],[-.25,-.25],[.25,.25],[-.25,.25],[.25,-.25],[-.25,0],[.25,0]];const patterns={1:[0],2:[1,2],3:[1,0,2],4:[1,2,3,4],5:[1,2,0,3,4],6:[1,2,5,6,3,4]};ctx.fillStyle='#17212b';for(const i of patterns[roll]||patterns[1]){const [px,py]=pip[i];ctx.beginPath();ctx.arc(px*size,py*size,size*.065,0,Math.PI*2);ctx.fill();}ctx.restore();
  glowText(ctx,`ROLL ${roll}`,w/2,h*.84,18,'#ffd84a');
}
function drawSlot(ctx,w,h,t,o){
  const reels=o?.reels||['🍒','🍋','⭐']; const spinning=t<900;
  const syms=['🍒','🍋','🔔','⭐','7️⃣'];ctx.save();
  const rw=Math.min(92,w*.25), rh=120, gap=10, sx=(w-(rw*3+gap*2))/2;
  for(let i=0;i<3;i++){let x=sx+i*(rw+gap);ctx.fillStyle='rgba(0,0,0,.55)';rr(ctx,x+5,h*.24+8,rw,rh,14);ctx.fill();let g=ctx.createLinearGradient(x,h*.22,x+rw,h*.22+rh);g.addColorStop(0,'#fafafa');g.addColorStop(.5,'#bfc4ca');g.addColorStop(1,'#656b73');ctx.fillStyle=g;rr(ctx,x,h*.22,rw,rh,14);ctx.fill();ctx.fillStyle='#121418';rr(ctx,x+7,h*.22+7,rw-14,rh-14,10);ctx.fill();const val=spinning?syms[Math.floor((t/70+i*2))%syms.length]:reels[i]||'7️⃣';glowText(ctx,val,x+rw/2,h*.22+rh/2,42,'#fff');}
  ctx.restore();glowText(ctx,'SPIN',w/2,h*.86,18,'#ffd84a');
}
function drawWheel(ctx,w,h,t,o){
  const prizes=Array.isArray(o?.prizes)&&o.prizes.length===10?o.prizes:[0,0,.5,1,1.2,1.5,2,3,5,10];
  const sector=Number(o?.sector||0), r=Math.min(w,h)*.30, cx=w/2,cy=h*.48, step=2*Math.PI/prizes.length;
  const startRot=1100*.025; let rot;
  if(sector>0&&t>=1100){let target=-Math.PI/2-((sector-1)+.5)*step;target+=Math.ceil((startRot-target)/(2*Math.PI))*2*Math.PI;const p=Math.min(1,(t-1100)/1000),ease=1-Math.pow(1-p,3);rot=startRot+(target-startRot)*ease;}
  else rot=t*.025;
  ctx.save();ctx.translate(cx,cy);ctx.rotate(rot);
  for(let i=0;i<prizes.length;i++){ctx.beginPath();ctx.moveTo(0,0);ctx.arc(0,0,r,i*step,(i+1)*step);ctx.closePath();ctx.fillStyle=i%2?'#8d1f2d':'#e0a928';ctx.fill();ctx.strokeStyle='#ffe58a';ctx.stroke();ctx.save();ctx.rotate((i+.5)*step);ctx.fillStyle='#fff';ctx.font='800 11px system-ui';ctx.textAlign='center';ctx.fillText(`${Number(prizes[i]).toFixed(2)}x`,r*.68,4);ctx.restore();}
  ctx.restore();ctx.fillStyle='#f7d35b';ctx.beginPath();ctx.moveTo(cx,cy-r-8);ctx.lineTo(cx-9,cy-r-24);ctx.lineTo(cx+9,cy-r-24);ctx.closePath();ctx.fill();glowText(ctx,o?.multiplier!==undefined?`${Number(o.multiplier).toFixed(2)}×`:'SPIN',cx,h*.86,20,'#ffd84a');
}
function drawKeno(ctx,w,h,t,o){
  // Backend outcome uses `draw` (the five drawn numbers), `selected` (the
  // player's five numbers) and `hits` as a COUNT. Normalize those shapes
  // here so the renderer never attempts `new Set(number)`.
  const chosen=new Set(Array.isArray(o?.chosen)?o.chosen:(Array.isArray(o?.selected)?o.selected:[]));
  const hitValues=Array.isArray(o?.hits)?o.hits:(Array.isArray(o?.draw)?o.draw.filter(n=>chosen.has(n)):[]);
  const hits=new Set(hitValues);
  const hitCount=Number.isFinite(Number(o?.hits))?Number(o.hits):hits.size;
  const cols=5, size=Math.min(44,(w-50)/5), gap=6, sx=(w-(cols*size+(cols-1)*gap))/2, sy=h*.18;
  for(let n=1;n<=20;n++){let i=n-1,x=sx+(i%cols)*(size+gap),y=sy+Math.floor(i/cols)*(size+gap);ctx.fillStyle=hits.has(n)?'#21d17a':chosen.has(n)?'#e0b52e':'#17232c';ctx.strokeStyle=hits.has(n)?'#a8ffd1':'#31424d';rr(ctx,x,y,size,size,9);ctx.fill();ctx.stroke();glowText(ctx,String(n),x+size/2,y+size/2,14,'#fff');}glowText(ctx,`HITS ${hitCount}`,w/2,h*.86,18,'#ffd84a');
}
function drawPathGame(ctx,w,h,t,o,key){
  const steps=Number(o?.steps||3), max=12, progress=Math.min(1,((t%1300)/1300)*.55+.35);const ground=h*.76;ctx.strokeStyle='rgba(255,220,130,.25)';ctx.lineWidth=2;for(let i=0;i<max;i++){let x=w*.12+i*w*.065;ctx.fillStyle=i<steps?'#b8862d':'#263238';rr(ctx,x,ground-(i%2)*8,42,28,7);ctx.fill();}
  const x=w*.12+(Math.min(steps,max)-1)*w*.065+21;const y=ground-20-Math.sin(progress*Math.PI)*65;ctx.font='44px serif';ctx.textAlign='center';ctx.fillText(key==='chicken'?'🐔':'🐇',x,y);glowText(ctx,`${steps} STEPS`,w/2,h*.88,18,'#ffd84a');
}
function drawCrash(ctx,w,h,t,o,key){
  const cash=Number(o?.cashout||0), crash=Number(o?.crash_point||o?.crash||0);const p=Math.min(1,t/1800);ctx.strokeStyle='#39d5ff';ctx.lineWidth=5;ctx.shadowColor='#39d5ff';ctx.shadowBlur=18;ctx.beginPath();ctx.moveTo(w*.10,h*.72);ctx.quadraticCurveTo(w*.42,h*.70,w*.18+w*.55*p,h*.72-h*.48*p);ctx.stroke();ctx.shadowBlur=0;ctx.font='42px serif';ctx.fillText(key==='aviator'?'✈️':'🚀',w*.18+w*.55*p-16,h*.72-h*.48*p-8);const shown=p<.95?Math.max(1.01,1+p*(Math.max(cash,crash||2)-1)):cash||crash||1.01;glowText(ctx,`${shown.toFixed(2)}×`,w/2,h*.30,42,'#fff');glowText(ctx,crash?`CRASH ${crash}×`:`CASHOUT ${cash}×`,w/2,h*.86,17,crash&&cash>crash?'#ff6b6b':'#ffd84a');
}
function drawPlinko(ctx,w,h,t,o){
  const rows=7, cols=8, sx=w/2, top=h*.18;ctx.fillStyle='#d7a936';for(let r=0;r<rows;r++)for(let c=0;c<=r;c++){let x=sx+(c-r/2)*34,y=top+r*32;ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();}
  const p=Math.min(1,t/1500), target=((o?.path||[]).reduce((a,b)=>a+(b?1:-1),0));let x=sx+target*8*p,y=top+(rows+1)*32*p;ctx.fillStyle='#c75cff';ctx.shadowColor='#e78bff';ctx.shadowBlur=20;ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;glowText(ctx,o?.multiplier!==undefined?`${o.multiplier}×`:'PLINKO',w/2,h*.88,19,'#ffd84a');
}
function drawMines(ctx,w,h,t,o){
  const cols=5,size=Math.min(52,(w-52)/5),gap=7,sx=(w-(cols*size+4*gap))/2,sy=h*.14,pick=Number(o?.pick||1);for(let n=1;n<=25;n++){let i=n-1,x=sx+(i%5)*(size+gap),y=sy+Math.floor(i/5)*(size+gap),open=t>700&&n===pick;ctx.fillStyle=open?(o?.safe?'#1fbd75':'#d83b52'):'#171c24';rr(ctx,x,y,size,size,10);ctx.fill();if(open)glowText(ctx,o?.safe?'💎':'💣',x+size/2,y+size/2,22,'#fff');else glowText(ctx,'?',x+size/2,y+size/2,16,'#66717d');}glowText(ctx,o?.safe?'SAFE':'MINES',w/2,h*.88,18,o?.safe?'#67e8a0':'#ff6b6b');
}
function drawFish(ctx,w,h,t,o){ctx.save();for(let i=0;i<7;i++){let x=((i*87+t*.05)% (w+80))-40,y=h*(.25+(i%4)*.14);ctx.font=`${22+i%3*5}px serif`;ctx.fillText(i%2?'🐠':'🐟',x,y);}ctx.strokeStyle='rgba(255,255,255,.16)';ctx.setLineDash([5,7]);ctx.beginPath();ctx.moveTo(w*.12,h*.74);ctx.lineTo(w*.88,h*.34);ctx.stroke();ctx.setLineDash([]);const hit=Math.max(1,Math.min(5,Number(o?.shot||1))),tx=w*(.14+(hit-1)*.18),ty=h*.60;ctx.strokeStyle=o?.safe?'#21d17a':'#ffd84a';ctx.lineWidth=3;ctx.beginPath();ctx.arc(tx,ty,18+Math.min(1,t/900)*7,0,Math.PI*2);ctx.stroke();ctx.font='30px serif';ctx.textAlign='center';ctx.fillText(o?.multiplier!==undefined&&Number(o.multiplier)>0?'🎯':'➤',tx,ty+8);glowText(ctx,o?.multiplier!==undefined?`${Number(o.multiplier).toFixed(2)}×`:'🎯',w/2,h*.84,21,'#ffd84a');ctx.restore();}
function drawCard(ctx,w,h,t,o){const card=o?.card||7, high=o?.choice==='high';ctx.save();ctx.translate(w/2,h*.46);ctx.rotate(Math.sin(Math.min(t,900)*.006)*.08);const cw=110,ch=150;ctx.shadowColor='rgba(0,0,0,.7)';ctx.shadowBlur=25;ctx.fillStyle='#f5f5f2';rr(ctx,-cw/2,-ch/2,cw,ch,12);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle=card>=8?'#b51f34':'#1e293b';ctx.font='900 42px system-ui';ctx.textAlign='center';ctx.fillText(String(card),0,15);ctx.font='28px serif';ctx.fillText(card%2?'♠':'♥',0,55);ctx.restore();glowText(ctx,(Number(o?.effective_multiplier)>1)?`WIN ${Number(o.effective_multiplier).toFixed(2)}×`:(o?.payout?`${Number(o.effective_multiplier||0).toFixed(2)}×`:(high?'HIGH':'LOW')),w/2,h*.86,18,'#ffd84a');}

function render3DScene(key, outcome={}, phase='result'){
  const token=(sceneState.get(key)||0)+1;sceneState.set(key,token);if(sceneRaf.has(key))cancelAnimationFrame(sceneRaf.get(key));const start=performance.now();
  const frame=(now)=>{if(sceneState.get(key)!==token)return;const sc=sceneCanvas(key);if(!sc)return;const {ctx,w,h}=sc;const t=now-start;sceneBase(ctx,w,h,key,t);switch(key){case'dice':drawDice(ctx,w,h,t,outcome);break;case'slot':drawSlot(ctx,w,h,t,outcome);break;case'wheel':drawWheel(ctx,w,h,t,outcome);break;case'keno':drawKeno(ctx,w,h,t,outcome);break;case'chicken':case'rabbit':drawPathGame(ctx,w,h,t,outcome,key);break;case'aviator':case'jet':drawCrash(ctx,w,h,t,outcome,key);break;case'plinko':drawPlinko(ctx,w,h,t,outcome);break;case'mines':drawMines(ctx,w,h,t,outcome);break;case'fish':drawFish(ctx,w,h,t,outcome);break;case'card':drawCard(ctx,w,h,t,outcome);break;}if(t<2200){sceneRaf.set(key,requestAnimationFrame(frame));}};sceneRaf.set(key,requestAnimationFrame(frame));
}

function init3DScene(key){ renderThreeGameScene(key,{},"idle"); }

function setupAddedGameControlsLegacy(key) {
  const el = document.getElementById(key + "-controls"); if (!el || el.dataset.ready) return;
  el.dataset.ready = "1";
  init3DScene(key);
  const stake = `<label>Bet (ብር)</label><input class="game-stake" id="${key}-stake" type="number" min="0.01" step="0.01" value="10">`;
  if (key === "dice") el.innerHTML = `${stake}<div class="choice-grid dice-board">${[1,2,3,4,5,6].map(n=>`<button class="choice-btn" data-value="${n}">🎲 ${n}</button>`).join("")}</div><input type="hidden" id="dice-value">`;
  if (key === "slot") el.innerHTML = `${stake}<div class="slot-board"><div class="slot-reel">7️⃣</div><div class="slot-reel">⭐</div><div class="slot-reel">🍒</div></div><small>3 server-authoritative reels • tap Play to spin</small>`;
  if (key === "wheel") el.innerHTML = `${stake}<div class="wheel-board">🎡<div class="wheel-pointer">▼</div></div><small>Server chooses the final sector; animation only visualizes it.</small>`;
  if (key === "keno") el.innerHTML = `${stake}<div class="kn-bar"><span id="kn-count">Picked 0 / 10</span><button type="button" id="kn-auto" class="kn-btn">Auto pick</button><button type="button" id="kn-clear" class="kn-btn">Clear</button></div><div class="choice-grid keno-grid kn80">${Array.from({length:80},(_,i)=>`<button class="choice-btn" data-value="${i+1}">${i+1}</button>`).join("")}</div><div id="kn-pay" class="kn-pay"><small>Pick 1–10 numbers · 20 balls are drawn from 80</small></div>`;
  if (key === "chicken") el.innerHTML = `${stake}<div class="road-board">${Array.from({length:12},(_,i)=>`<span class="road-step" data-step="${i+1}">${i+1}</span>`).join("")}</div><label>ደረጃ (Easy የሚመከር: 1)</label><input id="chicken-steps" type="number" min="1" max="12" value="1">`;
  if (key === "aviator") el.innerHTML = `${stake}<div class="crash-board">✈️ <strong id="aviator-live-mult">1.00×</strong></div><label>Auto Cash-out (optional)</label><input id="aviator-cashout" type="number" min="1.01" max="100" step="0.01" value="" placeholder="2.00 (empty = manual)">`;
  if (key === "jet") el.innerHTML = `${stake}<div class="crash-board jet-board">🚀 <strong id="jet-live-mult">1.00×</strong></div><label>Auto Cash-out (optional)</label><input id="jet-cashout" type="number" min="1.01" max="100" step="0.01" value="" placeholder="2.00 (empty = manual)">`;
  if (key === "plinko") el.innerHTML = `${stake}<div class="pl-opts"><div class="pl-grp"><span>Risk</span><button type="button" class="pl-opt" data-risk="low">Low</button><button type="button" class="pl-opt on" data-risk="med">Medium</button><button type="button" class="pl-opt" data-risk="high">High</button></div><div class="pl-grp"><span>Rows</span><button type="button" class="pl-opt" data-rows="8">8</button><button type="button" class="pl-opt on" data-rows="12">12</button><button type="button" class="pl-opt" data-rows="16">16</button></div></div><small>Fair binomial drop • exact multipliers are shown on the board</small>`;
  if (key === "mines") el.innerHTML = `${stake}<label>Mines</label><input id="mines-count" type="number" min="1" max="8" value="3"><div class="mines-board">${Array.from({length:25},(_,i)=>`<button class="mine-cell" data-cell="${i+1}">?</button>`).join("")}</div><input type="hidden" id="mines-pick" value="1"><small>Choose one cell; server determines whether it is safe.</small>`;
  if (key === "fish") el.innerHTML = `${stake}<div class="fish-board">${Array.from({length:5},(_,i)=>`<button class="fish-target" data-shot="${i+1}">${i%2?'🐠':'🐟'}</button>`).join("")}</div><input type="hidden" id="fish-shot" value="1"><small>Pick a target; server resolves the shot.</small>`;
  if (key === "coinflip") el.innerHTML = `${stake}<div class="card-table"><div class="playing-card-back">🪙</div><div class="choice-grid"><button class="choice-btn" data-value="heads">🪙 HEADS</button><button class="choice-btn" data-value="tails">🪙 TAILS</button></div></div>`;
  if (key === "penalty") el.innerHTML = `${stake}<div class="card-table"><div class="playing-card-back">🥅</div><div class="choice-grid"><button class="choice-btn" data-value="left">⬅ LEFT</button><button class="choice-btn" data-value="center">⬆ CENTER</button><button class="choice-btn" data-value="right">➡ RIGHT</button></div></div>`;
  if (key === "card") el.innerHTML = `${stake}<div class="card-table"><div class="playing-card-back">🂠</div><div class="choice-grid"><button class="choice-btn" data-value="high">⬆ HIGH</button><button class="choice-btn" data-value="low">⬇ LOW</button></div></div>`;
  const payoutNote=document.createElement("small"); payoutNote.className="payout-disclosure-note"; payoutNote.textContent="Payout multiplier = actual payout ÷ stake. Results show the effective multiplier after the configured RTP adjustment."; el.appendChild(payoutNote);
  el.querySelectorAll(".choice-btn").forEach(btn => btn.addEventListener("click", () => {
    if (key === "keno") {
      const selected = [...el.querySelectorAll(".choice-btn.selected")];
      if (!btn.classList.contains("selected") && selected.length >= 10) return;
      btn.classList.toggle("selected");
    } else {
      el.querySelectorAll(".choice-btn").forEach(b=>b.classList.remove("selected")); btn.classList.add("selected");
      if (key === "dice") document.getElementById("dice-value").value = btn.dataset.value;
    }
    haptic("light"); gameSound("tap");
  }));
  el.querySelectorAll(".road-step").forEach(btn=>btn.addEventListener("click",()=>{const id=key+"-steps";document.getElementById(id).value=btn.dataset.step;el.querySelectorAll(".road-step").forEach(x=>x.classList.remove("selected"));btn.classList.add("selected");gameSound("tap");haptic("light");}));
  el.querySelectorAll(".mine-cell").forEach(btn=>btn.addEventListener("click",()=>{el.querySelectorAll(".mine-cell").forEach(x=>x.classList.remove("selected"));btn.classList.add("selected");document.getElementById("mines-pick").value=btn.dataset.cell;gameSound("tap");haptic("light");}));
  el.querySelectorAll(".fish-target").forEach(btn=>btn.addEventListener("click",()=>{el.querySelectorAll(".fish-target").forEach(x=>x.classList.remove("selected"));btn.classList.add("selected");document.getElementById("fish-shot").value=btn.dataset.shot;gameSound("tap");haptic("light");}));
  const histBtn = document.getElementById(key+"-history-toggle");
  histBtn.addEventListener("click", async()=>{ const box=document.getElementById(key+"-history"); box.style.display=box.style.display==="none"?"block":"none"; if(box.style.display==="block") loadAddedHistory(key); });
  document.getElementById(key+"-play").addEventListener("click", ()=>playAddedGame(key));
}

function animateGameResult(key, result, won, outcome) {
  result.classList.remove("game-result-win", "game-result-lose", "result-dice", "result-slot", "result-wheel", "result-keno", "result-chicken", "result-aviator", "result-plinko", "result-mines", "result-jet", "result-fish", "result-rabbit", "result-card");
  result.classList.add(won ? "game-result-win" : "game-result-lose", "result-" + key);
  if (key === "slot") {
    const reels = outcome?.reels || [];
    result.innerHTML = `<div class="slot-reels-3d">${reels.map(x=>`<span>${escapeHtml(x)}</span>`).join("")}</div>` + result.innerHTML;
  } else if (key === "dice" && outcome?.roll) {
    result.innerHTML = `<div class="dice-result-3d">🎲 <b>${escapeHtml(outcome.roll)}</b></div>` + result.innerHTML;
  } else if (key === "wheel" && outcome?.multiplier !== undefined) {
    result.innerHTML = `<div class="wheel-result-3d">🎡 <b>${escapeHtml(outcome.multiplier)}×</b></div>` + result.innerHTML;
  }
  render3DScene(key, outcome, won ? "win" : "lose"); renderThreeGameScene(key, outcome, won ? "win" : "lose");
  const scene=document.getElementById(key+"-scene");
  if(scene){ scene.classList.remove("scene-win","scene-lose","scene-playing"); scene.classList.add(won?"scene-win":"scene-lose"); }
}

async function loadAddedHistory(key) {
  const box=document.getElementById(key+"-history"); try { const r=await apiFetch(`/games/${key}/history?limit=15`); box.innerHTML=(r.items||[]).map(x=>`<div class="history-row">${escapeHtml(x.created_at)} — ${x.status} — stake ${Number(x.stake).toFixed(2)} — payout ${Number(x.payout).toFixed(2)}</div>`).join("")||"ምንም ታሪክ የለም"; } catch(e){ box.textContent=e.message; }
}


let activeCategory = "all";

function renderGameGrid(filter = "") {
  const grid = document.getElementById("game-grid");
  grid.innerHTML = "";
  const q = filter.trim().toLowerCase();
  const visible = GAMES.filter((g) => {
    if (q && !g.name.toLowerCase().includes(q)) return false;
    if (activeCategory !== "all" && !g.cats.includes(activeCategory)) return false;
    return true;
  });

  if (!visible.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><span class="empty-emoji">🔍</span>ምንም ውጤት አልተገኘም</div>`;
    return;
  }

  for (const g of visible) {
    const card = document.createElement("div");
    card.className = "game-card";
    card.style.setProperty("--card-c1", g.color);
    card.style.setProperty("--card-c2", g.color2);
    card.innerHTML = `
      ${g.badge ? `<span class="game-badge">${g.badge}</span>` : ""}
      <div class="game-thumb game-thumb-${g.key}" aria-hidden="true">
        <div class="preview-stars"></div>
        <div class="preview-track"></div>
        <div class="preview-orb preview-orb-a"></div>
        <div class="preview-orb preview-orb-b"></div>
        <div class="preview-game-object">${g.icon}</div>
        <div class="preview-spark preview-spark-a"></div>
        <div class="preview-spark preview-spark-b"></div>
        <span class="preview-live-tag">${g.key === "keno" ? "READY" : g.key === "chicken" || g.key === "rabbit" ? "ROUND LIVE" : g.key === "fish" ? "FISHING" : g.key === "aviator" || g.key === "jet" ? "LIVE" : "PLAY NOW"}</span>
        <strong class="preview-multiplier">${({aviator:"2.40×",jet:"5.20×",chicken:"1.35×",rabbit:"1.20×",keno:"1.50×",fish:"2.00×",plinko:"3.00×",mines:"SAFE",slot:"777",wheel:"10×",dice:"6",coinflip:"2×",penalty:"GOAL",card:"WIN",boom:"2.00×",number:"WIN",sports:"LIVE",marketplace:"NEW"})[g.key] || "PLAY"}</strong>
        <span class="preview-caption">${g.key === "aviator" || g.key === "jet" ? "FLIGHT" : g.key === "chicken" || g.key === "rabbit" ? "ROAD RUN" : g.key === "keno" ? "PICK NUMBERS" : g.key === "fish" ? "UNDERWATER" : g.key === "plinko" ? "DROP BALL" : g.key === "wheel" ? "SPIN" : g.key === "card" ? "HIGH / LOW" : g.key === "mines" ? "FIND SAFE" : g.key === "slot" ? "777 REELS" : g.key === "dice" ? "ROLL" : g.key === "sports" ? "SPORTS" : g.key === "marketplace" ? "MARKET" : g.key === "boom" ? "BOOM" : "PLAY"}</span>
      </div>
      <div class="game-name">${g.name}</div>`;
    card.addEventListener("click", () => goToPage(g.key));
    grid.appendChild(card);
  }
}

function setupCategoryChips() {
  document.querySelectorAll("#category-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#category-chips .chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.dataset.cat;
      renderGameGrid(document.getElementById("game-search").value);
    });
  });
}

// ------------------------------------------------------------
// PAGE NAVIGATION (Lobby / Boom / Number / Sports / Wallet / Invite / Profile)
// ------------------------------------------------------------

function goToPage(page) {
  ensureAddedGamePages();
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  document.getElementById("page-" + page).classList.add("active");

  document.querySelectorAll("#bottom-nav button").forEach((b) => b.classList.remove("active"));
  const navMap = { boom: "lobby", number: "lobby", admin: "profile", lobby: "sports" }; // sub-pages keep their parent tab highlighted
  const navKey = navMap[page] || page;
  const navBtn = document.querySelector(`#bottom-nav button[data-page="${navKey}"]`);
  if (navBtn) navBtn.classList.add("active");

  // Boom needs live polling only while its page is actually open --
  // otherwise we'd be hammering the API in the background forever.
  if (page === "boom") startBoomPolling();
  else stopBoomPolling();

  if (page === "sports") loadSports();
  if (page === "number") loadNumberGameInfo();
  if (ADDED_GAME_INFO[page]) setupAddedGameControls(page);
  if (page === "marketplace") {
    loadMarketplace();
    startMarketplaceAutoRefresh();
  }
  if (page === "wallet") loadDepositInfo();
  if (page === "invite") loadInvite();
  if (page === "admin") loadAdminPanel();
}

function setupNav() {
  document.querySelectorAll("#bottom-nav button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => goToPage(btn.dataset.page));
  });
  document.querySelectorAll(".quick-cabinet-btn[data-quick-page]").forEach((btn) => {
    btn.addEventListener("click", () => goToPage(btn.dataset.quickPage));
  });
  document.getElementById("top-profile-btn")?.addEventListener("click", () => goToPage("profile"));
  document.getElementById("top-notification-btn")?.addEventListener("click", () => goToPage("profile"));
  document.getElementById("top-menu-btn")?.addEventListener("click", () => goToPage("profile"));
  document.querySelectorAll(".cabinet-tab[data-cat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".cabinet-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.dataset.cat;
      renderGameGrid(document.getElementById("game-search").value);
    });
  });
  document.querySelectorAll(".view-all-btn[data-cat-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeCategory = btn.dataset.catView;
      document.querySelectorAll(".cabinet-tab").forEach((b) => b.classList.toggle("active", b.dataset.cat === activeCategory));
      renderGameGrid(document.getElementById("game-search").value);
    });
  });
  document.querySelectorAll(".back-btn[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => goToPage(btn.dataset.back));
  });
  document.getElementById("game-search").addEventListener("input", (e) => {
    renderGameGrid(e.target.value);
  });
}

// ------------------------------------------------------------
// WALLET SUB-TABS
// ------------------------------------------------------------

function setupWalletSubtabs() {
  document.querySelectorAll("#wallet-subtabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#wallet-subtabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".wsub").forEach((s) => s.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("wsub-" + btn.dataset.wsub).classList.add("active");
      if (btn.dataset.wsub === "history" && historyPage === 0) loadHistory(true);
    });
  });
}

// ------------------------------------------------------------
// HISTORY
// ------------------------------------------------------------

function renderHistorySkeleton() {
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  for (let i = 0; i < 4; i++) {
    const li = document.createElement("li");
    li.className = "skeleton-card";
    li.innerHTML = `<div class="skeleton-line" style="width:70%"></div><div class="skeleton-line" style="width:40%;margin-bottom:0"></div>`;
    list.appendChild(li);
  }
}

function renderHistoryItems(items) {
  const list = document.getElementById("history-list");
  if (!items.length && historyPage === 0) {
    list.innerHTML = `<div class="empty-state"><span class="empty-emoji">📭</span>እስካሁን ምንም ግብይት የለም</div>`;
    return;
  }
  for (const it of items) {
    const li = document.createElement("li");
    const sign = it.amount >= 0 ? "+" : "";
    li.innerHTML = `
      <span>${it.label}<br><small>${it.created_at}</small></span>
      <strong style="color:${it.amount >= 0 ? "#1fae5c" : "#e53935"}">${sign}${it.amount.toFixed(2)}</strong>
    `;
    list.appendChild(li);
  }
}

async function loadHistory(reset = false) {
  if (reset) {
    historyPage = 0;
    renderHistorySkeleton();
  }
  const data = await apiFetch(`/history?page=${historyPage}`);
  historyTotal = data.total;
  if (reset) document.getElementById("history-list").innerHTML = "";
  renderHistoryItems(data.items);
  historyPage += 1;

  const moreBtn = document.getElementById("history-more");
  moreBtn.style.display = historyPage * data.per_page < historyTotal ? "block" : "none";
}

// ------------------------------------------------------------
// SPORTS
// ------------------------------------------------------------

// Original club crest generated from the team NAME (no external logos / no trademarks): same name -> same crest.
function teamCrest(name, size = 40, logo = "") {
  if (logo) {   // admin-uploaded club logo
    return `<img class="team-crest team-logo" src="${escapeHtml(String(API_BASE).replace(/\/api\/?$/, "") + logo)}" width="${size}" height="${size}" alt="" style="object-fit:contain;border-radius:8px" onerror="this.style.display='none'">`;
  }
  const n = String(name || "?").trim() || "?";
  let h = 0; for (const c of n.toLowerCase()) h = (h * 33 + c.charCodeAt(0)) >>> 0;
  const hue = h % 360, hue2 = (hue + 35 + (h >> 8) % 60) % 360, pat = (h >> 3) % 4, id = "c" + h.toString(36);
  const words = n.split(/\s+/).filter(Boolean);
  const ini = ((words.length > 1 ? words[0][0] + words[1][0] : n.slice(0, 2)) || "?").toUpperCase();
  const c1 = `hsl(${hue} 75% 45%)`, c2 = `hsl(${hue2} 80% 62%)`;
  const shield = "M32 4 L58 12 V32 C58 46 47 56 32 62 C17 56 6 46 6 32 V12 Z";
  const deco = pat === 0 ? `<rect x="6" y="4" width="13" height="60" fill="${c2}" opacity=".85"/><rect x="32" y="4" width="13" height="60" fill="${c2}" opacity=".85"/>`
    : pat === 1 ? `<rect x="6" y="22" width="52" height="11" fill="${c2}" opacity=".9"/><rect x="6" y="42" width="52" height="8" fill="${c2}" opacity=".6"/>`
    : pat === 2 ? `<path d="M6 40 L58 12 V26 L6 54 Z" fill="${c2}" opacity=".9"/>`
    : `<circle cx="32" cy="30" r="22" fill="${c2}" opacity=".35"/>`;
  return `<svg class="team-crest" width="${size}" height="${size}" viewBox="0 0 64 68" aria-hidden="true"><defs><clipPath id="${id}"><path d="${shield}"/></clipPath></defs>
    <path d="${shield}" fill="${c1}"/><g clip-path="url(#${id})">${deco}</g><path d="${shield}" fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round"/>
    <text x="32" y="40" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="900" font-size="22" fill="#fff" stroke="rgba(0,0,0,.55)" stroke-width="3" paint-order="stroke">${escapeHtml(ini)}</text></svg>`;
}

let sportsFilter = "all";
let sportsSlip = null;   // { match, sel }

async function loadSports() {
  const list = document.getElementById("sports-list");
  list.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    const li = document.createElement("li");
    li.className = "skeleton-card";
    li.innerHTML = `<div class="skeleton-line" style="width:60%"></div><div class="skeleton-line" style="width:100%;margin-bottom:0"></div>`;
    list.appendChild(li);
  }
  const data = await apiFetch("/sports/matches");
  const page = list.parentElement;

  // filter tabs (created once)
  let tabs = document.getElementById("sb-tabs");
  if (!tabs) {
    tabs = document.createElement("div"); tabs.id = "sb-tabs"; tabs.className = "sb-tabs";
    page.insertBefore(tabs, list);
    tabs.addEventListener("click", (e) => { const b = e.target.closest("button[data-f]"); if (!b) return; sportsFilter = b.dataset.f; paint(); });
  }
  let slip = document.getElementById("sb-slip");
  if (!slip) { slip = document.createElement("div"); slip.id = "sb-slip"; slip.className = "sb-slip"; slip.hidden = true; page.appendChild(slip); }

  const all = data.matches || [];
  sportsSlip = null; slip.hidden = true;

  function closeSlip() { sportsSlip = null; slip.hidden = true; list.querySelectorAll(".sb-opt.on").forEach((x) => x.classList.remove("on")); }

  function openSlip(m, sel, btn) {
    sportsSlip = { m, sel };
    list.querySelectorAll(".sb-opt.on").forEach((x) => x.classList.remove("on")); btn.classList.add("on");
    const odds = Number(sel === "HOME" ? m.odds_home : sel === "DRAW" ? m.odds_draw : m.odds_away);
    const label = sel === "HOME" ? `${m.home_team} ያሸንፋል` : sel === "AWAY" ? `${m.away_team} ያሸንፋል` : "አቻ (Draw)";
    slip.hidden = false;
    slip.innerHTML = `
      <div class="sb-slip-head"><b>🎫 የእርስዎ ምርጫ</b><button type="button" class="sb-x" aria-label="close">✕</button></div>
      <div class="sb-slip-pick"><span>${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)}</span><b>${escapeHtml(label)} <em>@ ${odds}</em></b></div>
      <input id="sb-stake" type="number" min="1" step="0.01" inputmode="decimal" placeholder="መጠን (ETB)">
      <div class="sb-chips"><button type="button" data-v="10">10</button><button type="button" data-v="50">50</button><button type="button" data-v="100">100</button><button type="button" data-v="max">Max</button></div>
      <div class="sb-ret">ግምታዊ ክፍያ: <b id="sb-ret">0.00</b> ብር</div>
      <button type="button" id="sb-place" class="sb-place">✅ ተወራረድ</button>
      <small id="sb-msg" class="bet-status"></small>`;
    const stake = slip.querySelector("#sb-stake"), ret = slip.querySelector("#sb-ret"), msg = slip.querySelector("#sb-msg");
    const upd = () => { const v = parseFloat(stake.value) || 0; ret.textContent = (v * odds).toFixed(2); };
    stake.addEventListener("input", upd);
    slip.querySelector(".sb-x").onclick = closeSlip;
    slip.querySelector(".sb-chips").onclick = (e) => {
      const c = e.target.closest("button[data-v]"); if (!c) return;
      stake.value = c.dataset.v === "max" ? String(Math.floor((window.__kdmBalance ? window.__kdmBalance() : 0) * 100) / 100) : c.dataset.v; upd();
    };
    slip.querySelector("#sb-place").onclick = async () => {
      const v = parseFloat(stake.value);
      if (!v || v <= 0) { msg.textContent = "❌ ትክክለኛ መጠን ያስገቡ"; return; }
      const pb = slip.querySelector("#sb-place"); pb.disabled = true;
      try {
        const r = await apiFetch("/sports/bet", { method: "POST", json: { match_id: m.id, selection: sel, stake: v } });
        msg.textContent = `✅ ${r.stake} ብር @ ${r.odds} -- ግምታዊ ክፍያ ${r.potential_payout} ብር (የመጨረሻው ክፍያ በpool ድርሻ ይወሰናል፤ ቤቱ ${Math.round((r.rake_pct || 0.08) * 100)}% ይወስዳል)`;
        haptic("success"); refreshBalance(); stake.value = ""; upd();
      } catch (e) { renderActionError(msg, e.message); haptic("error"); }
      finally { pb.disabled = false; }
    };
    slip.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function paint() {
    const liveN = all.filter((m) => m.live).length, upN = all.length - liveN;
    tabs.innerHTML = `<button data-f="all" class="${sportsFilter === "all" ? "on" : ""}">ሁሉም (${all.length})</button>
      <button data-f="live" class="${sportsFilter === "live" ? "on" : ""}">🔴 LIVE (${liveN})</button>
      <button data-f="up" class="${sportsFilter === "up" ? "on" : ""}">⏳ ቀጣይ (${upN})</button>`;
    const shown = all.filter((m) => sportsFilter === "all" || (sportsFilter === "live" ? m.live : !m.live));
    closeSlip(); list.innerHTML = "";
    if (!shown.length) {
      list.innerHTML = `<div class="empty-state"><span class="empty-emoji">⚽</span>${all.length ? "በዚህ ምድብ ውስጥ ግጥሚያ የለም" : "ንቁ ግጥሚያ የለም -- ቆይተው ይመልከቱ"}</div>`;
      return;
    }
    for (const m of shown) {
      const li = document.createElement("li");
      li.className = "sb-card" + (m.live ? " match-live" : "");
      const mid = m.live
        ? `<span class="live-pill"><i></i>LIVE${m.live_minute ? " · " + escapeHtml(m.live_minute) : ""}</span><b class="live-score">${m.home_score ?? 0} - ${m.away_score ?? 0}</b>`
        : `<span class="sb-vs">VS</span>`;
      const kick = String(m.closes_at || "").slice(5, 16).replace("-", "/");
      li.innerHTML = `
        <div class="sb-top"><span>⚽ እግር ኳስ</span><span>${m.live ? "🔴 በቀጥታ" : "🕒 " + escapeHtml(kick)}</span></div>
        <div class="sb-teams">
          <div class="sb-team">${teamCrest(m.home_team, 46, m.home_logo)}<b>${escapeHtml(m.home_team)}</b></div>
          <div class="sb-mid">${mid}</div>
          <div class="sb-team">${teamCrest(m.away_team, 46, m.away_logo)}<b>${escapeHtml(m.away_team)}</b></div>
        </div>
        ${m.live ? '<div class="live-closed">🔒 ጨዋታው ተጀምሯል -- Betting ዝግ ነው</div>' : ""}
        <div class="sb-odds">
          <button type="button" class="sb-opt" data-sel="HOME" ${m.live ? "disabled" : ""}><i>1</i><b>${m.odds_home}</b></button>
          <button type="button" class="sb-opt" data-sel="DRAW" ${m.live ? "disabled" : ""}><i>X</i><b>${m.odds_draw}</b></button>
          <button type="button" class="sb-opt" data-sel="AWAY" ${m.live ? "disabled" : ""}><i>2</i><b>${m.odds_away}</b></button>
        </div>`;
      li.querySelectorAll(".sb-opt").forEach((btn) => btn.addEventListener("click", () => {
        if (btn.classList.contains("on")) { closeSlip(); return; }
        openSlip(m, btn.dataset.sel, btn); haptic("light");
      }));
      list.appendChild(li);
    }
  }
  paint();
}

// ------------------------------------------------------------
// MARKETPLACE (🛍️ consulting/coaching services -- photo report,
// video review, video/audio call, sold via the same escrow flow
// the backend already exposes at /api/marketplace/*)
// ------------------------------------------------------------

const MARKETPLACE_TYPE_LABELS = {
  photo: "📷 PHOTO",
  video: "🎥 VIDEO",
  voice: "🎤 VOICE",
  consult_photo: "📷 PHOTO REPORT",
  consult_video: "🎥 VIDEO",
  video_call: "📹 LIVE VIDEO CALL",
  audio_call: "📞 LIVE AUDIO CALL",
};

let marketplaceRefreshTimer = null;
let marketplaceRefreshInFlight = false;

function startMarketplaceAutoRefresh() {
  if (marketplaceRefreshTimer) return;
  marketplaceRefreshTimer = setInterval(async () => {
    const page = document.getElementById("page-marketplace");
    if (!page || !page.classList.contains("active") || marketplaceRefreshInFlight) return;
    marketplaceRefreshInFlight = true;
    try { await loadMarketplace(); } finally { marketplaceRefreshInFlight = false; }
  }, 10000);
}

let marketplaceCategory = "";
async function loadMarketplace() {
  const list = document.getElementById("marketplace-list");
  list.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    const div = document.createElement("div");
    div.className = "skeleton-card";
    div.innerHTML = `<div class="skeleton-line" style="width:50%"></div><div class="skeleton-line" style="width:90%;margin-bottom:0"></div>`;
    list.appendChild(div);
  }

  try {
    const params = new URLSearchParams(); const qEl=document.getElementById("mkt-search"); if(qEl&&qEl.value.trim()) params.set("q",qEl.value.trim()); if(marketplaceCategory) params.set("category",marketplaceCategory); const sortEl=document.getElementById("mkt-sort"); if(sortEl) params.set("sort",sortEl.value);
    const data = await apiFetch("/marketplace/services" + (params.toString()?"?"+params.toString():""));
    list.innerHTML = "";
    if (!data.services.length) {
      list.innerHTML = `<div class="empty-state"><span class="empty-emoji">🛍️</span>ገና ምንም አገልግሎት አልተለጠፈም</div>`;
      return;
    }
    for (const s of data.services) {
      const card = document.createElement("div");
      card.className = "market-card";
      const ratingLine = s.avg_rating != null
        ? `<div class="market-rating">⭐ ${s.avg_rating} (${s.review_count} ግምገማ)</div>`
        : `<div class="market-rating market-rating-none">☆ ገና ግምገማ የለውም</div>`;
      const durationLine = s.duration_minutes ? `⏱️ ${s.duration_minutes} ደቂቃ` : "";
      const mediaBadge = s.sample_media_type ? (s.sample_media_type === "photo" ? "📷" : s.sample_media_type === "video" ? "🎬" : "🎤") : "📞";
      const gallery = (s.media_urls && s.media_urls.length) ? s.media_urls.map((u,i)=>{
        const mt=(s.media_items&&s.media_items[i]&&s.media_items[i].media_type)||s.sample_media_type;
        if(mt==='photo') return `<img class="mkt-feed-media" src="${escapeHtml(u)}" alt="Marketplace media ${i+1}" loading="lazy" draggable="false">`;
        if(mt==='video') return `<video class="mkt-feed-media" controls controlsList="nodownload noplaybackrate" preload="metadata" playsinline src="${escapeHtml(u)}"></video>`;
        return `<audio class="mkt-feed-audio" controls controlsList="nodownload" preload="metadata" src="${escapeHtml(u)}"></audio>`;
      }).join('') : '';
      card.innerHTML = `
        <div class="mkt-netflix-poster">
          ${gallery || (!s.media_url ? `<div class="mkt-call-poster">${mediaBadge}</div>` : "")}
          <div class="mkt-poster-gradient"></div>
          <span class="badge-type">${escapeHtml(MARKETPLACE_TYPE_LABELS[s.service_type] || s.service_type)}</span>
        </div>
        <div class="market-title">${escapeHtml(s.title)}</div>
        <div class="mkt-meta-row"><span>${escapeHtml(s.category || "General")}</span><span>${durationLine}</span></div>
        ${s.description ? `<div class="market-description">${escapeHtml(s.description)}</div>` : ""}

        ${ratingLine}
        <div class="market-price">💰 ${Number(s.price || 0).toFixed(2)} ብር</div>
        <div class="mkt-card-actions"><button class="market-open">▶ ዝርዝር ይመልከቱ</button><button class="market-buy">🔒 ግዛ</button></div>
        ${s.sample_file_id ? `<button class="market-view-sample">📲 Telegram ላይ ይላክ</button>` : ""}
        ${(s.service_type === "video_call" || s.service_type === "audio_call") ? `<div class="fairness-note">📞 ግዢ ከፈጸሙ በኋላ የCall ግንኙነት በTelegram ይላካል።</div>` : ""}
        ${s.review_count ? '<button class="market-view-reviews">📝 ግምገማዎች</button>' : ""}
        <button class="market-report">🚩 Report</button>
        <div class="market-reviews-panel" style="display:none"></div>
        <small class="market-status"></small>
      `;
      const statusEl = card.querySelector(".market-status");
      const buyBtn = card.querySelector(".market-buy");
      const openBtn = card.querySelector(".market-open");
      if (openBtn) openBtn.addEventListener("click", () => openMarketplaceDetail(s));
      buyBtn.addEventListener("click", async () => {
        if (!confirm(`"${s.title}" ን በ ${s.price} ብር ለመግዛት እርግጠኛ ነዎት? ገንዘቡ በ Escrow ይያዛል።`)) return;
        buyBtn.disabled = true;
        buyBtn.classList.add("btn-loading");
        try {
          const r = await apiFetch("/marketplace/buy", { method: "POST", json: { post_id: s.post_id } });
          statusEl.textContent = `✅ ${r.message} (Tx: ${r.tx_id})`;
          haptic("success");
          refreshBalance();
        } catch (e) {
          renderActionError(statusEl, e.message);
          haptic("error");
        } finally {
          buyBtn.disabled = false;
          buyBtn.classList.remove("btn-loading");
        }
      });
      const sampleBtn = card.querySelector(".market-view-sample");
      if (sampleBtn) {
        sampleBtn.addEventListener("click", async () => {
          sampleBtn.disabled = true;
          try {
            await apiFetch(`/marketplace/sample/${s.post_id}`, { method: "POST", json: {} });
            statusEl.textContent = "✅ Sample ወደ Telegram chat ተልኳል";
            haptic("success");
          } catch (e) {
            statusEl.textContent = "❌ " + escapeHtml(e.message);
          } finally { sampleBtn.disabled = false; }
        });
      }
      const reviewsBtn = card.querySelector(".market-view-reviews");
      if (reviewsBtn) {
        const reviewsPanel = card.querySelector(".market-reviews-panel");
        let reviewsLoaded = false;
        reviewsBtn.addEventListener("click", async () => {
          const isOpen = reviewsPanel.style.display !== "none";
          if (isOpen) {
            reviewsPanel.style.display = "none";
            reviewsBtn.textContent = "📝 ግምገማዎች ይመልከቱ";
            return;
          }
          reviewsPanel.style.display = "block";
          reviewsBtn.textContent = "📝 ግምገማዎች ደብቅ";
          if (reviewsLoaded) return;
          reviewsPanel.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
          try {
            const rv = await apiFetch(`/marketplace/services/${s.post_id}/reviews`);
            reviewsLoaded = true;
            reviewsPanel.innerHTML = rv.reviews.length
              ? rv.reviews.map((r) => `
                  <div class="review-row">
                    <div>${"⭐".repeat(r.rating)}${"☆".repeat(5 - r.rating)} <small>${escapeHtml(r.created_at)}</small></div>
                    ${r.comment ? `<div class="review-comment">${escapeHtml(r.comment)}</div>` : ""}
                  </div>
                `).join("")
              : `<div class="empty-state">ገና ግምገማ የለም</div>`;
          } catch (e) {
            reviewsPanel.innerHTML = `<div class="empty-state">❌ ${escapeHtml(e.message)}</div>`;
          }
        });
      }
      const social=document.createElement("div"); social.className="mkt-social-actions"; social.innerHTML=`<button class="mkt-like">${s.liked?"❤️":"🤍"} ${s.like_count||0}</button><button class="mkt-save">${s.saved?"🔖":"📑"} ${s.save_count||0}</button><button class="mkt-comments">💬 ${s.comment_count||0}</button><button class="mkt-share">↗️ Share</button><button class="mkt-creator">👤 ${escapeHtml(s.creator_first_name||s.creator_username||"Creator")}</button>`; card.insertBefore(social, card.querySelector(".market-report"));
      card.querySelector(".mkt-like").onclick=async()=>{try{const r=await apiFetch(`/marketplace/post/${s.post_id}/like`,{method:"POST",json:{}}); card.querySelector(".mkt-like").textContent=`${r.liked?"❤️":"🤍"} ${r.like_count}`;}catch(e){statusEl.textContent="❌ "+e.message;}};
      card.querySelector(".mkt-save").onclick=async()=>{try{const r=await apiFetch(`/marketplace/post/${s.post_id}/save`,{method:"POST",json:{}}); card.querySelector(".mkt-save").textContent=`${r.saved?"🔖":"📑"} ${r.save_count}`;}catch(e){statusEl.textContent="❌ "+e.message;}};
      card.querySelector(".mkt-comments").onclick=async()=>{try{const rv=await apiFetch(`/marketplace/post/${s.post_id}/comments`); const text=rv.comments.length?rv.comments.map(c=>`${c.first_name||c.username||"User"}: ${c.comment}`).join("\n"):"No comments"; const c=prompt(text+"\n\nWrite a comment:"); if(c&&c.trim()) {await apiFetch(`/marketplace/post/${s.post_id}/comments`,{method:"POST",json:{comment:c.trim()}}); loadMarketplace();}}catch(e){statusEl.textContent="❌ "+e.message;}};
      card.querySelector(".mkt-share").onclick=async()=>{const url=location.href+`#marketplace-${s.post_id}`; try{if(navigator.share) await navigator.share({title:s.title,text:s.description||s.title,url}); else await navigator.clipboard.writeText(url); statusEl.textContent="✅ Shared";}catch(e){}};
      card.querySelector(".mkt-creator").onclick=async()=>{try{const r=await apiFetch(`/marketplace/creator/${s.creator_id}`); const c=r.creator; const action=confirm(`${c.first_name||c.username||"Creator"}\n⭐ ${r.avg_rating||"-"} | 👥 ${r.followers} | 📦 ${r.post_count}\n\n${r.following?"Unfollow":"Follow"} this creator?`); if(action){const f=await apiFetch(`/marketplace/creator/${s.creator_id}/follow`,{method:"POST",json:{}}); statusEl.textContent=`${f.following?"✅ Followed":"✅ Unfollowed"} (${f.followers})`;}}catch(e){statusEl.textContent="❌ "+e.message;}};
      apiFetch(`/marketplace/post/${s.post_id}/view`,{method:"POST",json:{}}).catch(()=>{});
      card.querySelector(".market-report").addEventListener("click", async () => {
        const reason = prompt("ችግሩን በአጭሩ ይግለጹ (ለምሳሌ፦ ተገቢ ያልሆነ ይዘት፣ አላቀረበም፣ አታላይ)፦");
        if (!reason || !reason.trim()) return;
        try {
          const r = await apiFetch("/marketplace/report", { method: "POST", json: { post_id: s.post_id, reason } });
          statusEl.textContent = "✅ " + r.message;
          haptic("success");
        } catch (e) {
          statusEl.textContent = "❌ " + e.message;
          haptic("error");
        }
      });
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

function openMarketplaceDetail(s) {
  const modal = document.getElementById("marketplace-detail-modal");
  const content = document.getElementById("mkt-detail-content");
  if (!modal || !content) return;
  const media = s.media_url && s.sample_media_type === "photo"
    ? `<img class="mkt-detail-media" src="${escapeHtml(s.media_url)}" alt="Marketplace media" draggable="false">`
    : s.media_url && s.sample_media_type === "video"
      ? `<video class="mkt-detail-media" controls controlsList="nodownload noplaybackrate" playsinline preload="metadata" src="${escapeHtml(s.media_url)}"></video>`
      : s.media_url && s.sample_media_type === "voice"
        ? `<audio class="mkt-detail-audio" controls controlsList="nodownload" src="${escapeHtml(s.media_url)}"></audio>`
        : `<div class="mkt-detail-call-icon">${s.service_type === "video_call" ? "📹" : s.service_type === "audio_call" ? "📞" : "🛍️"}</div>`;
  content.innerHTML = `<div class="mkt-detail-media-wrap">${media}</div><span class="badge-type">${escapeHtml(MARKETPLACE_TYPE_LABELS[s.service_type] || s.service_type)}</span><h2>${escapeHtml(s.title)}</h2><div class="mkt-meta-row"><span>👤 ${escapeHtml(s.creator_first_name || s.creator_username || "Creator")}</span><span>🏷️ ${escapeHtml(s.category || "General")}</span><span>${s.duration_minutes ? `⏱️ ${s.duration_minutes} min` : ""}</span></div><p>${escapeHtml(s.description || "")}</p><div class="market-price">💰 ${Number(s.price || 0).toFixed(2)} ብር</div>${s.avg_rating != null ? `<div class="market-rating">⭐ ${s.avg_rating} (${s.review_count} ግምገማ)</div>` : ""}<button class="market-buy mkt-detail-buy">🔒 በ Escrow ግዛ</button>${s.sample_file_id ? `<button class="market-view-sample mkt-detail-telegram">📲 Telegram ላይ ይላክ</button>` : ""}<small class="market-status mkt-detail-status"></small>`;
  modal.style.display = "block"; document.body.classList.add("mkt-modal-open");
  const close = () => { modal.style.display = "none"; document.body.classList.remove("mkt-modal-open"); };
  document.getElementById("mkt-detail-close").onclick = close; modal.querySelector(".mkt-detail-backdrop").onclick = close;
  content.querySelector(".mkt-detail-buy").onclick = async () => { const btn=content.querySelector(".mkt-detail-buy"); if(!confirm(`"${s.title}" ን በ ${s.price} ብር ለመግዛት እርግጠኛ ነዎት?`)) return; btn.disabled=true; try { const r=await apiFetch("/marketplace/buy",{method:"POST",json:{post_id:s.post_id}}); content.querySelector(".mkt-detail-status").textContent=`✅ ${r.message}`; refreshBalance(); haptic("success"); } catch(e){ content.querySelector(".mkt-detail-status").textContent="❌ "+e.message; haptic("error"); } finally { btn.disabled=false; } };
  const tg=content.querySelector(".mkt-detail-telegram"); if(tg) tg.onclick=async()=>{try{await apiFetch(`/marketplace/sample/${s.post_id}`,{method:"POST",json:{}});content.querySelector(".mkt-detail-status").textContent="✅ Telegram ላይ ተልኳል";}catch(e){content.querySelector(".mkt-detail-status").textContent="❌ "+e.message;}};
}

function setupMarketplaceTabs() {
  document.querySelectorAll(".mkt-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".mkt-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".mkt-panel-section").forEach((s) => s.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("mkt-" + tab.dataset.mktTab).classList.add("active");
      if (tab.dataset.mktTab === "my-services") loadMyServices();
      if (tab.dataset.mktTab === "my-sales") loadMySales();
      if (tab.dataset.mktTab === "my-purchases") loadMyPurchases();
    });
  });

  const search=document.getElementById("mkt-search"); if(search){ let t; search.addEventListener("input",()=>{clearTimeout(t); t=setTimeout(loadMarketplace,300);}); }
  const sort=document.getElementById("mkt-sort"); if(sort) sort.addEventListener("change",loadMarketplace);
  document.querySelectorAll(".mkt-cat").forEach(btn=>btn.addEventListener("click",()=>{document.querySelectorAll(".mkt-cat").forEach(x=>x.classList.remove("active"));btn.classList.add("active");marketplaceCategory=btn.dataset.cat||"";loadMarketplace();}));
  const createBtn = document.getElementById("mkt-create-btn");
  const typeSelect = document.getElementById("mkt-new-type");
  const sampleInput = document.getElementById("mkt-new-sample");
  const syncMarketplaceSampleAccept = () => {
    const t = typeSelect.value;
    sampleInput.accept = t === "photo" ? "image/*" : (t === "video" ? "video/*" : (t === "voice" ? "audio/*" : ""));
    sampleInput.disabled = t === "video_call" || t === "audio_call";
    if (sampleInput.disabled) sampleInput.value = "";
  };
  typeSelect.addEventListener("change", syncMarketplaceSampleAccept);
  syncMarketplaceSampleAccept();
  createBtn.addEventListener("click", async () => {
    const title = document.getElementById("mkt-new-title").value.trim();
    const service_type = document.getElementById("mkt-new-type").value;
    const description = document.getElementById("mkt-new-description").value.trim();
    const category = document.getElementById("mkt-new-category").value;
    const duration_minutes = parseInt(document.getElementById("mkt-new-duration").value || "0", 10) || null;
    const price = parseFloat(document.getElementById("mkt-new-price").value);
    const samples = Array.from(document.getElementById("mkt-new-sample").files || []); const sample = samples[0];
    const statusEl = document.getElementById("mkt-create-status");
    if (!title) { statusEl.textContent = "❌ ርዕስ ያስፈልጋል"; return; }
    if (!price || price <= 0) { statusEl.textContent = "❌ ትክክለኛ ዋጋ ያስፈልጋል"; return; }
    if (!duration_minutes) { statusEl.textContent = "❌ የቆይታ ጊዜ (ደቂቃ) ያስገቡ"; return; }
    if (["photo","video","voice"].includes(service_type) && !sample) { statusEl.textContent = "❌ Photo/Video/Voice post ላይ media ያስገቡ"; return; }
    if ((service_type === "video_call" || service_type === "audio_call") && sample) { statusEl.textContent = "❌ Live Call ላይ sample አያስፈልግም"; return; }

    createBtn.disabled = true;
    createBtn.classList.add("btn-loading");
    try {
      const fd = new FormData();
      fd.append("title", title);
      fd.append("service_type", service_type);
      fd.append("description", description);
      fd.append("category", category);
      fd.append("duration_minutes", String(duration_minutes));
      fd.append("price", String(price));
      samples.forEach(f => fd.append("sample", f));
      const created = await apiFetch("/marketplace/my-services", { method: "POST", formData: fd });
      statusEl.textContent = created && created.visible
        ? "✅ Post ታትሟል — አሁን ለሁሉም በ Marketplace ይታያል።"
        : "🕒 Post ተልኳል — Admin ሲያጸድቀው ለሁሉም ይታያል። ሁኔታውን በ «የእኔ አገልግሎቶች» ውስጥ ይከታተሉ።";
      haptic("success");
      document.getElementById("mkt-new-title").value = "";
      document.getElementById("mkt-new-description").value = "";
      document.getElementById("mkt-new-price").value = "";
      document.getElementById("mkt-new-duration").value = "";
      document.getElementById("mkt-new-sample").value = "";
      loadMyServices();
      loadMarketplace();
    } catch (e) {
      statusEl.textContent = "❌ " + e.message;
      haptic("error");
    } finally {
      createBtn.disabled = false;
      createBtn.classList.remove("btn-loading");
    }
  });
}

async function loadMyServices() {
  const list = document.getElementById("mkt-my-services-list");
  list.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  try {
    const data = await apiFetch("/marketplace/my-services");
    list.innerHTML = "";
    if (!data.services.length) {
      list.innerHTML = `<div class="empty-state">ገና ምንም አገልግሎት አልጨመሩም</div>`;
      return;
    }
    for (const s of data.services) {
      const card = document.createElement("div");
      card.className = "market-card";
      card.innerHTML = `
        <span class="badge-type">${escapeHtml(MARKETPLACE_TYPE_LABELS[s.service_type] || s.service_type)}</span>
        ${s.active ? "" : '<span class="admin-disabled-tag">ንቁ አይደለም</span>'}
        ${(() => { const m = s.moderation_status || "pending";
          return m === "approved" ? '<div class="mkt-delivery-tag">✅ ለሁሉም ይታያል</div>'
            : m === "rejected" ? `<div class="mkt-delivery-tag mkt-delivery-pending">❌ ውድቅ ተደርጓል${s.moderation_note ? " -- " + escapeHtml(s.moderation_note) : ""}</div>`
            : '<div class="mkt-delivery-tag mkt-delivery-pending">🕒 በግምገማ ላይ -- ገና ለሌሎች አይታይም</div>'; })()}
        <label>የፖስት ርዕስ</label>
        <input type="text" class="mkt-edit-title" maxlength="120" value="${escapeHtml(s.title || "")}">
        <label>መግለጫ</label>
        <textarea class="mkt-edit-description" maxlength="1000" rows="3">${escapeHtml(s.description || "")}</textarea>
        <label>ካታጎሪ</label>
        <input type="text" class="mkt-edit-category" maxlength="60" value="${escapeHtml(s.category || "General")}">
        <label>የአገልግሎት አይነት</label>
        <select class="mkt-edit-type">${Object.entries(MARKETPLACE_TYPE_LABELS).map(([k,v]) => `<option value="${escapeHtml(k)}" ${s.service_type===k?"selected":""}>${escapeHtml(v)}</option>`).join("")}</select>
        <label>ዋጋ (ብር)</label>
        <input type="number" class="mkt-edit-price" value="${Number(s.price)||1}" step="0.01" min="1">
        <label>የቆይታ ጊዜ (ደቂቃ)</label>
        <input type="number" class="mkt-edit-duration" value="${s.duration_minutes || ""}" min="1" max="1440" placeholder="ካልተፈለገ ባዶ ይተዉ">
        ${s.sample_file_id ? `<div class="mkt-delivery-tag">☁️ Sample በ Telegram storage ተቀምጧል</div>` : ""}
        <div class="admin-btn-row">
          <button class="mkt-save-price">💾 ሁሉንም አዘምን</button>
          <button class="mkt-toggle-active">${s.active ? "⏸️ አቁም" : "▶️ አንቃ"}</button>
        </div>
        <small class="mkt-edit-status"></small>
      `;
      const statusEl = card.querySelector(".mkt-edit-status");
      card.querySelector(".mkt-save-price").addEventListener("click", async () => {
        const price = parseFloat(card.querySelector(".mkt-edit-price").value);
        try {
          const title = card.querySelector(".mkt-edit-title").value.trim();
          const description = card.querySelector(".mkt-edit-description").value.trim();
          const category = card.querySelector(".mkt-edit-category").value.trim();
          const service_type = card.querySelector(".mkt-edit-type").value;
          const durationRaw = card.querySelector(".mkt-edit-duration").value;
          const duration_minutes = durationRaw === "" ? null : Number(durationRaw);
          if (!title || !Number.isFinite(price) || price < 1 || (duration_minutes !== null && (!Number.isInteger(duration_minutes) || duration_minutes < 1 || duration_minutes > 1440))) {
            throw new Error("ርዕስ፣ ዋጋ እና የቆይታ ጊዜ ትክክለኛ ያድርጉ");
          }
          await apiFetch(`/marketplace/my-services/${s.post_id}`, { method: "POST", json: { title, description, category, service_type, price, duration_minutes } });
          statusEl.textContent = "✅ ለማረጋገጫ ተልኳል፤ እስኪፈቀድ ድረስ ፖስቱ አይታይም";
          haptic("success");
        } catch (e) {
          statusEl.textContent = "❌ " + e.message;
        }
      });
      card.querySelector(".mkt-toggle-active").addEventListener("click", async () => {
        try {
          await apiFetch("/marketplace/my-services/update", { method: "POST", json: { post_id: s.post_id, active: !s.active } });
          loadMyServices();
        } catch (e) {
          statusEl.textContent = "❌ " + e.message;
        }
      });
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

async function startEmbeddedCall(txId, serviceType) {
  const info=await apiFetch('/calls/session',{method:'POST',json:{tx_id:txId}});
  const sid=info.session_id, modal=document.createElement('div'); modal.className='mkt-call-modal';
  modal.innerHTML=`<div class="mkt-call-box"><div class="mkt-call-head"><b>${serviceType==='video_call'?'📹 Live Video Call':'📞 Live Audio Call'}</b><button class="mkt-call-close">✕</button></div><video class="mkt-call-remote" autoplay playsinline></video><video class="mkt-call-local" autoplay muted playsinline></video><div class="mkt-call-status">🔄 Connecting…</div><button class="mkt-call-end">⛔ End Call</button></div>`;document.body.appendChild(modal);
  const status=modal.querySelector('.mkt-call-status'),remote=modal.querySelector('.mkt-call-remote'),local=modal.querySelector('.mkt-call-local');if(serviceType==='audio_call'){local.style.display='none';remote.style.display='none';}
  if(!window.RTCPeerConnection||!navigator.mediaDevices?.getUserMedia){status.textContent='❌ WebRTC አይደገፍም';return;}
  const pc=new RTCPeerConnection({iceServers:info.ice_servers||[{urls:'stun:stun.l.google.com:19302'}]});let last=0,closed=false,stream=null;
  const send=(type,payload)=>apiFetch(`/calls/${encodeURIComponent(sid)}/signal`,{method:'POST',json:{type,payload}});
  const cleanup=async()=>{if(closed)return;closed=true;if(stream)stream.getTracks().forEach(t=>t.stop());pc.close();await apiFetch(`/calls/${encodeURIComponent(sid)}/end`,{method:'POST',json:{}}).catch(()=>{});modal.remove();};
  modal.querySelector('.mkt-call-close').onclick=cleanup;modal.querySelector('.mkt-call-end').onclick=cleanup;
  try{stream=await navigator.mediaDevices.getUserMedia(serviceType==='video_call'?{video:true,audio:true}:{video:false,audio:true});local.srcObject=stream;stream.getTracks().forEach(t=>pc.addTrack(t,stream));pc.ontrack=e=>{remote.srcObject=e.streams[0];status.textContent='🟢 Connected';};pc.onicecandidate=e=>{if(e.candidate)send('candidate',e.candidate.toJSON()).catch(()=>{});};
    if(info.role==='buyer'){const offer=await pc.createOffer();await pc.setLocalDescription(offer);await send('offer',offer);status.textContent='📡 Waiting for creator…';}else status.textContent='📡 Waiting for buyer…';
    const poll=async()=>{if(closed)return;try{const r=await apiFetch(`/calls/${encodeURIComponent(sid)}/signals?after=${last}`);for(const x of r.signals||[]){last=Math.max(last,x.id);if(x.signal_type==='offer'&&info.role==='seller'){await pc.setRemoteDescription(x.payload);const ans=await pc.createAnswer();await pc.setLocalDescription(ans);await send('answer',ans);}else if(x.signal_type==='answer'&&info.role==='buyer'){await pc.setRemoteDescription(x.payload);}else if(x.signal_type==='candidate'){try{await pc.addIceCandidate(x.payload);}catch(_){}}}}catch(_){}if(!closed)setTimeout(poll,500);};poll();
  }catch(e){status.textContent='❌ '+e.message;pc.close();}
}

async function loadMyPurchases() {
  const list = document.getElementById("mkt-my-purchases-list");
  list.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  try {
    const data = await apiFetch("/marketplace/my-purchases");
    list.innerHTML = "";
    if (!data.purchases.length) {
      list.innerHTML = `<div class="empty-state">ገና ምንም ግዢ የለም</div>`;
      return;
    }
    for (const p of data.purchases) {
      const card = document.createElement("div");
      card.className = "market-card";
      const statusLabel = { held_in_escrow: "🔒 በ Escrow ተይዟል", completed: "✅ ተጠናቋል", refunded: "↩️ ተመላሽ ተደርጓል" }[p.status] || p.status;
      const deliveryLabel = { photo: "📷 Photo", video: "🎥 Video", voice: "🎤 Voice" }[p.delivery_type];
      card.innerHTML = `
        <div class="market-title">${escapeHtml(p.title || "(deleted service)")}</div>
        <div class="market-price">💰 ${p.amount.toFixed(2)} ብር -- ${statusLabel}</div>
        <small>${escapeHtml(p.created_at)}</small>
        ${p.delivered_at
          ? `<div class="mkt-delivery-tag">✅ ${deliveryLabel} ደርሶዎታል -- Telegram chat ውስጥ ይመልከቱ</div>${p.status === "held_in_escrow" ? `<button class="mkt-confirm-receipt">✅ አገልግሎቱን ተቀብያለሁ</button>` : ""}`
          : (p.status === "held_in_escrow" && (p.service_type === "video_call" || p.service_type === "audio_call"))
            ? `<button class="mkt-request-contact">📞 ግንኙነት ጠይቅ</button>`
            : (p.status === "held_in_escrow" ? `<div class="mkt-delivery-tag mkt-delivery-pending">⏳ ገና አልደረሰም</div>` : "")
        }
        <small class="market-status"></small>
      `;
      const confirmReceiptBtn = card.querySelector(".mkt-confirm-receipt");
      if (confirmReceiptBtn) confirmReceiptBtn.addEventListener("click", async () => {
        if (!confirm("አገልግሎቱን ተቀብለዋል? ካረጋገጡ በኋላ escrow ለአቅራቢው ይለቀቃል።")) return;
        confirmReceiptBtn.disabled = true;
        try {
          await apiFetch("/marketplace/confirm-receipt", {method:"POST", json:{tx_id:p.tx_id}});
          haptic("success"); loadMyPurchases();
        } catch (e) {
          card.querySelector(".market-status").textContent = "❌ " + escapeHtml(e.message);
          confirmReceiptBtn.disabled = false;
        }
      });
      const requestContactBtn = card.querySelector(".mkt-request-contact");
      if (requestContactBtn) {
        requestContactBtn.addEventListener("click", async () => {
          requestContactBtn.disabled = true;
          try {
            await startEmbeddedCall(p.tx_id, p.service_type);
            requestContactBtn.disabled = false;
            haptic("success");
          } catch (e) {
            card.querySelector(".market-status").textContent = "❌ " + escapeHtml(e.message);
            requestContactBtn.disabled = false;
          }
        });
      }
      if (p.status === "completed" && !p.reviewed) {
        card.innerHTML += `
          <div class="mkt-review-form">
            <select class="mkt-review-rating">
              <option value="5">⭐⭐⭐⭐⭐ (5)</option>
              <option value="4">⭐⭐⭐⭐ (4)</option>
              <option value="3">⭐⭐⭐ (3)</option>
              <option value="2">⭐⭐ (2)</option>
              <option value="1">⭐ (1)</option>
            </select>
            <input type="text" class="mkt-review-comment" placeholder="አስተያየት (አማራጭ)">
            <button class="mkt-review-submit">✍️ ግምገማ ላክ</button>
          </div>
          <small class="mkt-review-status"></small>
        `;
        card.querySelector(".mkt-review-submit").addEventListener("click", async () => {
          const rating = parseInt(card.querySelector(".mkt-review-rating").value);
          const comment = card.querySelector(".mkt-review-comment").value.trim();
          const statusEl = card.querySelector(".mkt-review-status");
          try {
            await apiFetch("/marketplace/review", { method: "POST", json: { tx_id: p.tx_id, rating, comment } });
            statusEl.textContent = "✅ ግምገማዎ ተልኳል";
            haptic("success");
            card.querySelector(".mkt-review-form").style.display = "none";
          } catch (e) {
            statusEl.textContent = "❌ " + e.message;
          }
        });
      } else if (p.reviewed) {
        card.innerHTML += `<small class="mkt-reviewed-tag">✅ ገምግመዋል</small>`;
      }
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

const MARKETPLACE_DELIVERY_ACCEPT = { photo: "image/*", video: "video/*", voice: "audio/*" };

async function loadMySales() {
  const list = document.getElementById("mkt-my-sales-list");
  list.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  try {
    const data = await apiFetch("/marketplace/my-sales");
    list.innerHTML = "";
    if (!data.sales.length) {
      list.innerHTML = `<div class="empty-state">ገና ምንም ሽያጭ የለም</div>`;
      return;
    }
    for (const s of data.sales) {
      const card = document.createElement("div");
      card.className = "market-card";
      const statusLabel = { held_in_escrow: "🔒 በ Escrow ተይዟል", completed: "✅ ተጠናቋል", refunded: "↩️ ተመላሽ ተደርጓል" }[s.status] || s.status;
      const buyerLabel = s.buyer_username ? `@${escapeHtml(s.buyer_username)}` : escapeHtml(s.buyer_first_name || `ID: ${s.buyer_id}`);
      const isCall = s.service_type === "video_call" || s.service_type === "audio_call";
      const deliveryLabel = { photo: "📷 Photo", video: "🎥 Video", voice: "🎤 Voice" }[s.delivery_type];

      card.innerHTML = `
        <div class="market-title">${escapeHtml(s.title || "(deleted service)")}</div>
        <small>ገዢ፦ ${buyerLabel} -- ${escapeHtml(s.created_at)}</small>
        <div class="market-price">💰 ${s.amount.toFixed(2)} ብር -- ${statusLabel}</div>
        ${s.delivered_at ? `<div class="mkt-delivery-tag">✅ ${deliveryLabel} ተልኳል</div>` : ""}
        <small class="mkt-deliver-status"></small>
      `;

      const statusEl = card.querySelector(".mkt-deliver-status");
      if (s.status === "held_in_escrow" && !s.delivered_at) {
        if (isCall) {
          const btn = document.createElement("button");
          btn.className = "mkt-request-contact";
          btn.textContent = "📞 ግንኙነት ጠይቅ";
          btn.addEventListener("click", async () => {
            btn.disabled = true;
            try {
              await startEmbeddedCall(s.tx_id, s.service_type);
              haptic("success");
            } catch (e) {
              statusEl.textContent = "❌ " + escapeHtml(e.message);
              btn.disabled = false;
            }
          });
          card.appendChild(btn);
        } else {
          // photo/video-report style listings -- creator attaches the
          // actual file here; it's relayed straight to the buyer's
          // Telegram chat and never touches our own disk.
          const form = document.createElement("div");
          form.className = "mkt-deliver-form";
          const defaultType = s.service_type === "consult_video" ? "video" : "photo";
          form.innerHTML = `
            <select class="mkt-deliver-type">
              <option value="photo" ${defaultType === "photo" ? "selected" : ""}>📷 Photo</option>
              <option value="video" ${defaultType === "video" ? "selected" : ""}>🎥 Video</option>
              <option value="voice">🎤 Voice</option>
            </select>
            <input type="file" class="mkt-deliver-file" accept="${MARKETPLACE_DELIVERY_ACCEPT[defaultType]}">
            <button class="mkt-deliver-submit">📤 አድርስ</button>
          `;
          const typeSel = form.querySelector(".mkt-deliver-type");
          const fileInput = form.querySelector(".mkt-deliver-file");
          typeSel.addEventListener("change", () => {
            fileInput.accept = MARKETPLACE_DELIVERY_ACCEPT[typeSel.value];
          });
          const submitBtn = form.querySelector(".mkt-deliver-submit");
          submitBtn.addEventListener("click", async () => {
            const file = fileInput.files[0];
            if (!file) { statusEl.textContent = "❌ ፋይል ይምረጡ"; return; }
            submitBtn.disabled = true;
            submitBtn.classList.add("btn-loading");
            statusEl.textContent = "";
            try {
              const fd = new FormData();
              fd.append("tx_id", s.tx_id);
              fd.append("media_type", typeSel.value);
              fd.append("file", file);
              await apiFetch("/marketplace/deliver", { method: "POST", formData: fd });
              statusEl.textContent = "✅ ተልኳል";
              haptic("success");
              form.remove();
              card.insertAdjacentHTML("beforeend", `<div class="mkt-delivery-tag">✅ ${escapeHtml(typeSel.value)} ተልኳል</div>`);
            } catch (e) {
              statusEl.textContent = "❌ " + escapeHtml(e.message);
              haptic("error");
            } finally {
              submitBtn.disabled = false;
              submitBtn.classList.remove("btn-loading");
            }
          });
          card.appendChild(form);
        }
      }
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = `<div class="empty-state">❌ ${escapeHtml(e.message)}</div>`;
  }
}



// ---- Boom Game client ---------------------------------------------------------------
// Fixes: (1) the board used to be rebuilt every second by the poll, which swallowed taps on phones
// and could re-enable buttons mid-request; (2) the round result (BOOM / WIN) was wiped by the very
// next poll because the server immediately opens a fresh round. Now the grid only re-renders when
// something actually changed, polls are ignored while a request is in flight, and a finished round's
// result is held on screen for a few seconds -- including rounds that someone ELSE ended.
let boomLastState = null;
let boomSig = "";
let boomHoldUntil = 0;
let boomBannerTimer = null;

function boomSignature(state) {
  return JSON.stringify([
    state.round_id, state.opened, state.game_over, state.my_status, state.result || "",
    Number(state.prize_pool || 0).toFixed(2), Number(state.your_win_amount || 0).toFixed(2),
    state.players.map((p) => p.name + ":" + p.status),
  ]);
}

function boomResultText(state) {
  if (!state.game_over) return "";
  if (state.my_status === "LOST") return "💥 BOOM! ቦምብ ተገኘ -- ተሸንፈዋል";
  if (state.my_status === "WIN") return "🏆 አሸነፉ! ሁሉም ደህንነታቸው የተጠበቁ ሳጥኖች ተከፍተዋል";
  if (state.my_status === "LEFT") return "🚪 ዙሩን ለቀዋል";
  return state.result === "BOOM" ? "💥 BOOM! ዙሩ አልቋል" : "ዙሩ አልቋል";
}

function renderBoom(state, force) {
  const sig = boomSignature(state);
  if (!force && sig === boomSig) return; // nothing changed -- leave the DOM (and any finger mid-tap) alone
  boomSig = sig;
  boomLastState = state;

  const info = document.getElementById("boom-info");
  const grid = document.getElementById("boom-grid");
  const joined = state.my_status === "playing";

  info.textContent = state.game_over
    ? boomResultText(state)
    : `Entry: ${state.entry_fee} ብር | 🏆 Pool: ${Number(state.prize_pool||0).toFixed(2)} ብር | ግምታዊ ድርሻ: ${Number(state.your_win_amount||0).toFixed(2)} ብር | Live Players: ${state.players.length} | ቤቱ ${Math.round((state.rake_pct||0.08)*100)}% ብቻ`;

  const commitEl = document.getElementById("boom-commitment");
  if (commitEl) commitEl.textContent = state.commitment ? state.commitment.slice(0, 16) + "…" : "-";

  const bombs = Array.isArray(state.bombs) ? state.bombs : [];
  const canPick = !state.game_over && (state.my_status === null || state.my_status === undefined || joined);
  grid.innerHTML = "";
  for (let i = 1; i <= 9; i++) {
    const btn = document.createElement("button");
    const isOpen = state.opened.includes(i);
    const isBomb = state.game_over && bombs.includes(i);
    btn.textContent = isBomb ? "💥" : isOpen ? "🎁" : i;
    if (isOpen) btn.classList.add("opened");
    if (isBomb) btn.classList.add("bomb");
    btn.disabled = isOpen || !canPick;
    btn.addEventListener("click", () => pickBoomBox(i));
    grid.appendChild(btn);
  }

  const leaveBtn = document.getElementById("boom-leave");
  if (leaveBtn) leaveBtn.disabled = !joined || state.game_over;

  const list = document.getElementById("boom-players");
  list.innerHTML = "";
  for (const p of state.players) {
    const li = document.createElement("li");
    li.innerHTML = `<span>👤 ${escapeHtml(p.name)}</span><span>${escapeHtml(p.status)}</span>`;
    list.appendChild(li);
  }
}

// Keep a finished round's result on screen for a few seconds before the next round replaces it.
function holdBoomResult(state, ms = 4500) {
  boomHoldUntil = Date.now() + ms;
  renderBoom(state, true);
  clearTimeout(boomBannerTimer);
  boomBannerTimer = setTimeout(() => { boomHoldUntil = 0; loadBoomState(); }, ms);
}

// A round ended while we were only watching (or after our last poll): fetch its final board from
// the fairness log so the player still sees what happened instead of the board just resetting.
async function showEndedRoundFor(prev) {
  try {
    const data = await apiFetch("/games/boom/history?limit=1");
    const r = data.rounds && data.rounds[0];
    if (!r || r.round_id !== prev.round_id) return;
    const lastOpened = r.opened[r.opened.length - 1];
    const hitBomb = r.bombs.includes(lastOpened);
    const mine = prev.my_status;
    holdBoomResult({
      ...prev, game_over: true, opened: r.opened, bombs: r.bombs,
      result: hitBomb ? "BOOM" : "WIN",
      my_status: mine === "playing" ? (hitBomb ? "LOST" : "WIN") : mine,
    });
    if (mine === "playing" && !hitBomb) { celebrateWin(); celebrateWin3D(); refreshBalance(); }
    if (mine === "playing" && hitBomb) { haptic("error"); refreshBalance(); }
  } catch (_) { /* history is best-effort; the next poll still shows the new round */ }
}

let boomSceneShown = false;
async function loadBoomState() {
  if (boomPickInFlight || Date.now() < boomHoldUntil) return; // don't fight an in-flight tap or the result banner
  if (!boomSceneShown) { boomSceneShown = true; renderThreeGameScene("boom", {}, "playing"); }
  try {
    const state = await apiFetch("/games/boom/state");
    if (boomPickInFlight || Date.now() < boomHoldUntil) return; // state changed while we were waiting
    const prev = boomLastState;
    if (prev && !prev.game_over && prev.round_id !== state.round_id) {
      showEndedRoundFor(prev); // the round we were looking at finished -- show how
      return;
    }
    renderBoom(state);
  } catch (e) {
    document.getElementById("boom-info").textContent = "❌ " + e.message;
  }
}

let boomPickInFlight = false;

async function pickBoomBox(box) {
  if (boomPickInFlight) return; // ignore rapid double-taps while a pick is still in flight
  const st = boomLastState;
  // The first tap silently joined the round and charged the entry fee. Ask first.
  if (st && !st.game_over && st.my_status !== "playing") {
    if (!window.confirm(`ወደ ዙሩ ለመግባት ${st.entry_fee} ብር ከሂሳብዎ ይቆረጣል። ይቀጥሉ?`)) return;
  }
  boomPickInFlight = true;
  const grid = document.getElementById("boom-grid");
  grid.querySelectorAll("button").forEach((b) => (b.disabled = true));

  try {
    const state = await apiFetch("/games/boom/pick", { method: "POST", json: { box } });
    haptic(state.result === "BOOM" ? "error" : "success");
    if (state.game_over) holdBoomResult(state); else renderBoom(state, true);
    if (state.result === "WIN") { celebrateWin(); celebrateWin3D(); }
    refreshBalance();
  } catch (e) {
    renderActionError(document.getElementById("boom-info"), e.message);
    haptic("error");
    boomPickInFlight = false;
    boomSig = ""; // force the resync below to repaint
    loadBoomState(); // resync -- our local view may be stale
  } finally {
    boomPickInFlight = false;
  }
}

async function leaveBoom() {
  try {
    if (!window.confirm("ከዙሩ ከወጡ የከፈሉት ክፍያ አይመለስም። መውጣት ይፈልጋሉ?")) return;
    const state = await apiFetch("/games/boom/leave", { method: "POST" });
    renderBoom(state, true);
  } catch (e) {
    document.getElementById("boom-info").textContent = "❌ " + e.message;
  }
}

function startBoomPolling() {
  stopBoomPolling();
  boomLastState = null; boomSig = ""; boomHoldUntil = 0; // fresh view every time the page is opened
  loadBoomState();
  boomPollTimer = setInterval(loadBoomState, 1000);
}

function stopBoomPolling() {
  clearTimeout(boomBannerTimer);
  if (boomPollTimer) {
    clearInterval(boomPollTimer);
    boomPollTimer = null;
  }
}

// ------------------------------------------------------------
// NUMBER GAME (🔢 instant solo round -- one guess, immediate result)
// ------------------------------------------------------------

function renderNumberGrid() {
  const grid = document.getElementById("number-grid");
  grid.innerHTML = "";
  for (let i = 1; i <= 15; i++) {
    const btn = document.createElement("button");
    btn.textContent = i;
    btn.addEventListener("click", () => playNumberGame(i));
    grid.appendChild(btn);
  }
}

let numberPollTimer = null;
let numberLastSeenRound = null;

function stopNumberPolling() { if (numberPollTimer) { clearInterval(numberPollTimer); numberPollTimer = null; } }

async function loadNumberGameInfo() {
  renderThreeGameScene("number",{},"idle");
  stopNumberPolling();
  await refreshNumberState();
  numberPollTimer = setInterval(() => {
    if (!document.getElementById("page-number")?.classList.contains("active")) { stopNumberPolling(); return; }
    refreshNumberState();
  }, 2000);
}

async function refreshNumberState() {
  const info = document.getElementById("number-info");
  const resultEl = document.getElementById("number-result");
  try {
    const settings = await apiFetch("/games/settings");
    const s = settings.number;
    const st = await apiFetch("/games/number/state");
    const mine = st.my_guess ? ` | ✅ የእርስዎ ቁጥር: ${st.my_guess}` : "";
    info.textContent = s.enabled
      ? `Entry: ${s.entry_fee} ብር | 🏆 Prize pool: ${Number(st.prize_pool).toFixed(2)} ብር | ⏱ ${st.seconds_left}s | ተጫዋቾች: ${st.entries}${mine} | ቤቱ ${Math.round(st.rake_pct*100)}% ብቻ ይወስዳል`
      : "🔴 Number Game አሁን ላይ ጠፍቷል";
    document.getElementById("number-grid").querySelectorAll("button")
      .forEach((b) => (b.disabled = !s.enabled || !!st.my_guess));
    const last = st.my_last;
    if (last && last.round_id !== numberLastSeenRound) {
      if (numberLastSeenRound !== null) {
        resultEl.textContent = last.status === "WON"
          ? `🎉 ቁጥሩ ${last.secret} ነበር -- ${Number(last.payout).toFixed(2)} ብር አሸንፈዋል!`
          : `❌ ቁጥሩ ${last.secret} ነበር (የእርስዎ ${last.guess})። pool ወደ ቀጣዩ ዙር ይተላለፋል።`;
        if (last.status === "WON") { haptic("success"); celebrateWin(); celebrateWin3D(); } else { haptic("error"); }
        refreshBalance();
      }
      numberLastSeenRound = last.round_id;
    }
  } catch (e) {
    info.textContent = "❌ " + e.message;
  }
}

async function playNumberGame(guess) {
  const grid = document.getElementById("number-grid");
  const resultEl = document.getElementById("number-result");
  grid.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    const r = await apiFetch("/games/number/play", { method: "POST", json: { guess } });
    resultEl.textContent = `✅ ቁጥር ${r.guess} ተመዝግቧል። ዙሩ ሲዘጋ ውጤቱ ይታያል (Prize pool: ${Number(r.prize_pool).toFixed(2)} ብር)።`;
    haptic("success");
    refreshBalance();
    refreshNumberState();
  } catch (e) {
    renderActionError(resultEl, e.message);
    haptic("error");
    refreshNumberState();
  }
}

// ------------------------------------------------------------
// DEPOSIT / WITHDRAW
// ------------------------------------------------------------

let depositInfoLoaded = false;

async function loadDepositInfo() {
  if (depositInfoLoaded) return;
  const info = await apiFetch("/deposit/info");
  const accounts = [
    { label: "👤", value: info.account_name, copyable: false },
    { label: "📱 Telebirr", value: info.telebirr, copyable: true },
    { label: "🏦 CBE", value: info.cbe, copyable: true },
    { label: "🏦 BOA", value: info.boa, copyable: true },
  ];
  const container = document.getElementById("deposit-accounts");
  container.innerHTML = "";
  for (const acc of accounts) {
    const row = document.createElement("div");
    row.className = "deposit-account-row";
    if (acc.copyable) {
      row.innerHTML = `<span>${escapeHtml(acc.label)}: ${escapeHtml(acc.value)}</span><button type="button" class="copy-account-btn">📋 ቅዳ</button>`;
      row.querySelector(".copy-account-btn").addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        try {
          await navigator.clipboard.writeText(acc.value);
          const original = btn.textContent;
          btn.textContent = "✅ ተቀድቷል";
          haptic("success");
          setTimeout(() => { btn.textContent = original; }, 1500);
        } catch (err) {
          btn.textContent = "⚠️ ይምረጡ";
        }
      });
    } else {
      row.innerHTML = `<span>${escapeHtml(acc.label)}: ${escapeHtml(acc.value)}</span>`;
    }
    container.appendChild(row);
  }
  depositInfoLoaded = true;
}

function setupDepositForm() {
  // Optional live Chapa checkout. Manual screenshot deposits remain available
  // as a fallback, but when Chapa is configured the wallet can be credited
  // only after server-side verification with Chapa.
  const form=document.getElementById("deposit-form");
  if(form && !document.getElementById("chapa-live-box")){
    const box=document.createElement("div"); box.id="chapa-live-box"; box.className="chapa-live-box";
    box.innerHTML=`<div><b>⚡ Online Deposit</b><small>Chapa checkout — server verification required</small></div><button type="button" id="chapa-pay-btn">💳 Pay Online</button><button type="button" id="chapa-verify-btn" style="display:none">🔎 Verify Payment</button><small id="chapa-status"></small>`;
    form.parentNode.insertBefore(box,form);
    apiFetch("/payments/chapa/status").then(st=>{box.style.display=st.configured?"flex":"none";}).catch(()=>{box.style.display="none";});
    document.getElementById("chapa-pay-btn").onclick=async()=>{
      const status=document.getElementById("chapa-status"), amount=Number(document.getElementById("deposit-amount").value);
      if(!(amount>0)){status.textContent="❌ Amount ያስገቡ";return;}
      const btn=document.getElementById("chapa-pay-btn");btn.disabled=true;status.textContent="⏳ Checkout እየተዘጋጀ...";
      try{const r=await apiFetch("/payments/chapa/initialize",{method:"POST",json:{amount}});try{localStorage.setItem("kdm_chapa_tx_ref",r.tx_ref);}catch(_){};const vb=document.getElementById("chapa-verify-btn");vb.style.display="inline-block";status.textContent=`✅ Checkout ready — ${r.tx_ref}`;if(tg.openLink)tg.openLink(r.checkout_url);else window.open(r.checkout_url,"_blank");}
      catch(e){status.textContent="❌ "+e.message;}finally{btn.disabled=false;}
    };
    document.getElementById("chapa-verify-btn").onclick=async()=>{const status=document.getElementById("chapa-status");let tx="";try{tx=localStorage.getItem("kdm_chapa_tx_ref")||"";}catch(_){};if(!tx){status.textContent="❌ tx_ref የለም";return;}try{const r=await apiFetch(`/payments/chapa/verify/${encodeURIComponent(tx)}`);status.textContent=r.credited?`✅ ${Number(r.amount).toFixed(2)} ብር Wallet ተሞልቷል`:`⏳ Payment ገና አልተረጋገጠም`;if(r.credited){try{localStorage.removeItem("kdm_chapa_tx_ref");}catch(_){};await refreshBalance();haptic("success");}}catch(e){status.textContent="❌ "+e.message;}};
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    let tx = ""; try { tx = localStorage.getItem("kdm_chapa_tx_ref") || ""; } catch (_) {}
    const vb = document.getElementById("chapa-verify-btn");
    if (tx && vb && vb.style.display !== "none") vb.click();
  });
  const fileInput = document.getElementById("deposit-screenshot");
  const preview = document.getElementById("deposit-preview");
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) {
      preview.style.display = "none";
      return;
    }
    preview.src = URL.createObjectURL(file);
    preview.style.display = "block";
  });

  document.getElementById("deposit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const statusEl = document.getElementById("deposit-status");
    const amount = document.getElementById("deposit-amount").value;
    const file = fileInput.files[0];
    if (!file) {
      statusEl.textContent = "❌ Screenshot ያስፈልጋል";
      return;
    }
    const fd = new FormData();
    fd.append("amount", amount);
    fd.append("screenshot", file);

    const submitBtn = e.target.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.classList.add("btn-loading");
    statusEl.textContent = "";
    try {
      const r = await apiFetch("/deposit", { method: "POST", formData: fd });
      statusEl.textContent = `✅ ተልኳል (Payment #${r.payment_id}) -- Admin ሲያጸድቅ Wallet ይሞላል።`;
      haptic("success");
      document.getElementById("deposit-form").reset();
      preview.style.display = "none";
      refreshBalance();
    } catch (e2) {
      statusEl.textContent = "❌ " + e2.message;
      haptic("error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove("btn-loading");
    }
  });
}

function setupWithdrawForm() {
  document.getElementById("withdraw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const statusEl = document.getElementById("withdraw-status");
    const amount = parseFloat(document.getElementById("withdraw-amount").value);
    const holder = document.getElementById("withdraw-name").value.trim();
    const acc_number = document.getElementById("withdraw-number").value.trim();
    const mBtn = document.querySelector("#withdraw-methods button.on");
    const method = mBtn ? mBtn.dataset.method : "";
    const bal = window.__kdmBalance ? window.__kdmBalance() : Infinity;

    if (!method) { statusEl.textContent = "❌ የማውጫ ዘዴ ይምረጡ (CBE / BOA / Telebirr)"; haptic("error"); return; }
    if (!amount || amount < 1) {
      statusEl.textContent = "❌ ዝቅተኛው የማውጫ መጠን 1 ብር ነው";
      return;
    }
    if (amount > bal) { statusEl.textContent = `❌ Balance በቂ አይደለም (${bal.toFixed(2)} ብር አለዎት)`; haptic("error"); return; }
    const acc_name = method + " | " + holder;
    const okText = `${amount.toFixed(2)} ብር ወደ ${method} ${acc_number} (${holder}) ይውጣ?`;
    const confirmed = await new Promise((res) => {
      if (tg && tg.showConfirm) tg.showConfirm(okText, res); else res(window.confirm(okText));
    });
    if (!confirmed) return;
    try {
      if (document.getElementById("withdraw-remember").checked)
        localStorage.setItem("kdm_wd_acc", JSON.stringify({ method, name: holder, number: acc_number }));
      else localStorage.removeItem("kdm_wd_acc");
    } catch (_) {}

    const submitBtn = e.target.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.classList.add("btn-loading");
    statusEl.textContent = "";
    try {
      const r = await apiFetch("/withdraw", { method: "POST", json: { amount, acc_name, acc_number } });
      statusEl.textContent = `✅ ጥያቄ ተልኳል (Withdrawal #${r.withdrawal_id}) -- Admin ሲፈጽም ያሳውቅዎታል። ሁኔታውን History ውስጥ ይከታተሉ።`;
      haptic("success");
      { const f = document.getElementById("withdraw-amount"); if (f) f.value = ""; }
      refreshBalance();
    } catch (e2) {
      const tm = /wager ([\d.]+)/.exec(e2.message || "");
      statusEl.textContent = tm ? `❌ ማውጣት ከመቻልዎ በፊት ተጨማሪ ${tm[1]} ብር መጫወት ያስፈልጋል (ከገቡት ገንዘብ 3× መጫወት ይጠበቃል)።` : "❌ " + e2.message;
      haptic("error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove("btn-loading");
    }
  });
}

// ------------------------------------------------------------
// INVITE
// ------------------------------------------------------------

async function loadInvite() {
  const statusEl = document.getElementById("invite-status");
  try {
    const r = await apiFetch("/referral");
    document.getElementById("invite-count").textContent = r.invited_count;
    const per = Number(r.bonus_per_invite ?? 1);
    const prog = document.getElementById("invite-progress"); if (prog) prog.textContent = `${Math.min(r.invited_count, 10)}/10`;
    const earn = document.getElementById("invite-earned"); if (earn) earn.textContent = Number(r.bonus_earned || 0).toFixed(2)
      + (r.bonus_after_deposit && r.pending_invites ? ` (+${r.pending_invites} ጓደኛ የመጀመሪያ ገንዘብ ሲያስገባ)` : "");
    const rule = document.getElementById("invite-bonus-rule"); if (rule) rule.textContent = `ለእያንዳንዱ ለጋበዙት ሰው ${per} ብር ቦነስ ያገኛሉ (10 ሰው = ${per * 10} ብር)።`;
    const linkInput = document.getElementById("invite-link");
    if (r.link) {
      linkInput.value = r.link;
      statusEl.textContent = "";
    } else {
      linkInput.value = "";
      statusEl.textContent = "⚠️ Referral link ገና አልተዋቀረም (Admin BOT_USERNAME ማዘጋጀት አለበት)።";
    }
  } catch (e) {
    statusEl.textContent = "❌ " + e.message;
  }
}

function setupInvite() {
  document.getElementById("invite-copy").addEventListener("click", async () => {
    const link = document.getElementById("invite-link").value;
    const statusEl = document.getElementById("invite-status");
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      statusEl.textContent = "✅ ተቀድቷል!";
      haptic("success");
    } catch (e) {
      statusEl.textContent = "⚠️ በእጅ ይምረጡ እና ይቅዱ";
    }
  });

  document.getElementById("invite-share").addEventListener("click", () => {
    const link = document.getElementById("invite-link").value;
    const statusEl = document.getElementById("invite-status");
    if (!link) return;
    const text = encodeURIComponent("🎉 King Bet 🥳 ተቀላቀል! ተጫወት፣ አሸንፍ 💰");
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${text}`;
    try {
      tg.openTelegramLink(shareUrl);
    } catch (e) {
      statusEl.textContent = "⚠️ Share አልተሳካም -- ሊንኩን ይቅዱ";
    }
  });
}

function setupLegalLinks() {
  ["terms-link", "terms-link-2"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", (e) => { e.preventDefault(); goToPage("terms"); });
  });
  ["privacy-link", "privacy-link-2"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", (e) => { e.preventDefault(); goToPage("privacy"); });
  });
}

// Verifies the provably-fair commit-reveal: anyone can run this same
// check themselves (it's just SHA-256, built into every browser) to
// confirm a revealed server_seed really does hash to the commitment
// that was shown BEFORE the round was played. Bomb positions
// themselves are derived from server_seed using Python's random
// module server-side, which isn't practical to reproduce in-browser
// -- verifying the seed/commitment match is the meaningful, checkable
// part: it proves the seed (and therefore the bombs it determines)
// was fixed in advance and not swapped after the fact.
async function sha256Hex(text) {
  const enc = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(hashBuffer)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function setupBoomHistory() {
  const toggle = document.getElementById("boom-history-toggle");
  const panel = document.getElementById("boom-history-panel");
  toggle.addEventListener("click", async () => {
    const showing = panel.style.display !== "none";
    if (showing) {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "block";
    const list = document.getElementById("boom-history-list");
    list.innerHTML = `<li class="skeleton-card"><div class="skeleton-line" style="width:80%"></div></li>`;
    try {
      const data = await apiFetch("/games/boom/history?limit=15");
      list.innerHTML = "";
      if (!data.rounds.length) {
        list.innerHTML = `<div class="empty-state"><span class="empty-emoji">📭</span>ገና የተጠናቀቀ ዙር የለም</div>`;
        return;
      }
      for (const r of data.rounds) {
        const li = document.createElement("li");
        const winner = r.players.find((p) => p.status === "WIN");
        const outcome = winner ? `🏆 ${escapeHtml(winner.name)} አሸነፈ` : "💥 ማንም አላሸነፈም";
        let verifyLine = "";
        if (r.server_seed && r.commitment) {
          const recomputed = await sha256Hex(r.server_seed);
          const verified = recomputed === r.commitment;
          verifyLine = `
            <div class="fairness-verify">
              ${verified ? "✅ ተረጋግጧል" : "❌ አልተመሳሰለም"}: SHA-256(seed) ${verified ? "==" : "!="} commitment<br>
              <code>seed: ${r.server_seed}</code>
            </div>`;
        }
        li.innerHTML = `
          <div class="fairness-row">
            <span>ዙር #${r.round_id} -- ${outcome}</span>
            <small>${r.created_at}</small>
          </div>
          <div class="fairness-bombs">💣 ቦምቦች የነበሩበት፦ ${r.bombs.join(", ")}</div>
          ${verifyLine}
        `;
        list.appendChild(li);
      }
    } catch (e) {
      list.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
    }
  });
}

function setupNumberHistory() {
  const toggle = document.getElementById("number-history-toggle");
  const panel = document.getElementById("number-history-panel");
  toggle.addEventListener("click", async () => {
    const showing = panel.style.display !== "none";
    if (showing) {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "block";
    const list = document.getElementById("number-history-list");
    list.innerHTML = `<li class="skeleton-card"><div class="skeleton-line" style="width:80%"></div></li>`;
    try {
      const data = await apiFetch("/games/number/history?limit=15");
      list.innerHTML = "";
      if (!data.rounds.length) {
        list.innerHTML = `<div class="empty-state"><span class="empty-emoji">📭</span>ገና የተጠናቀቀ ዙር የለም</div>`;
        return;
      }
      for (const r of data.rounds) {
        const li = document.createElement("li");
        const outcome = r.won
          ? `🏆 ${escapeHtml(r.name)} አሸነፈ (+${r.payout.toFixed(2)} ብር)`
          : `❌ ${escapeHtml(r.name)} አላሸነፈም`;
        li.innerHTML = `
          <div class="fairness-row">
            <span>${outcome}</span>
            <small>${r.created_at}</small>
          </div>
          <div class="fairness-bombs">🎯 ገመተው፦ ${r.guess} -- ትክክለኛ ቁጥር፦ ${r.secret}</div>
        `;
        list.appendChild(li);
      }
    } catch (e) {
      list.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
    }
  });
}

function setupSelfExclusion() {
  const toggle = document.getElementById("self-exclude-toggle");
  const panel = document.getElementById("self-exclude-panel");
  toggle.addEventListener("click", () => {
    panel.style.display = panel.style.display === "none" ? "block" : "none";
  });

  document.querySelectorAll(".self-exclude-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const days = parseInt(btn.dataset.days);
      const statusEl = document.getElementById("self-exclude-status");
      const ok = confirm(
        `⚠️ እርግጠኛ ነዎት? ለ${days} ቀናት እራስዎን ካገዱ በኋላ ጊዜው እስኪያልቅ ድረስ ማንም (አስተዳዳሪም ቢሆን) መክፈት አይችልም። ይህ ውሳኔ የማይቀለበስ ነው።`
      );
      if (!ok) return;
      try {
        const r = await apiFetch("/self-exclude", { method: "POST", json: { days } });
        statusEl.textContent = `✅ እራስዎን እስከ ${r.self_excluded_until} ድረስ አግደዋል።`;
        setTimeout(() => { try { tg.close(); } catch (e) {} }, 2500);
      } catch (e) {
        statusEl.textContent = "❌ " + e.message;
      }
    });
  });
}

// ------------------------------------------------------------
// 18+ AGE GATE
// Hard block: nothing in #content is shown, and main() (which starts
// making API calls) is not even invoked, until the user confirms.
// Declining shows a dead-end screen instead of the app.
// ------------------------------------------------------------

function ageGatePassed() {
  try { return localStorage.getItem("kdm_age_confirmed_v2") === "1"; }
  catch (e) { return false; }
}

function runAgeGate(onPassed) {
  if (ageGatePassed()) {
    onPassed();
    return;
  }
  const overlay = document.getElementById("age-gate-overlay");
  overlay.style.display = "flex";

  document.getElementById("age-gate-confirm").addEventListener("click", async () => {
    try { localStorage.setItem("kdm_age_confirmed_v2", "1"); } catch (e) { /* ignore */ }
    // Best-effort -- records WHEN this user agreed (server-side,
    // timestamped) rather than relying only on the client-side
    // localStorage flag as evidence of consent. Never blocks the
    // flow if it fails (e.g. a network hiccup shouldn't stop
    // someone from using the app).
    try {
      await apiFetch("/accept-terms", { method: "POST" });
      overlay.style.display = "none";
      onPassed();
    } catch (e) {
      try { localStorage.removeItem("kdm_age_confirmed_v2"); } catch (_) {}
      document.getElementById("age-gate-confirm").disabled = false;
      document.getElementById("age-gate-confirm").textContent = "❌ ማረጋገጫ አልተመዘገበም — እንደገና ይሞክሩ";
    }
  }, { once: true });

  document.getElementById("age-gate-decline").addEventListener("click", () => {
    overlay.style.display = "none";
    document.getElementById("age-gate-blocked").style.display = "block";
    try { tg.close(); } catch (e) { /* not running inside Telegram */ }
  }, { once: true });
}

// ------------------------------------------------------------
// BOOTSTRAP
// ------------------------------------------------------------

// ------------------------------------------------------------
// ADMIN PANEL (staff only -- every call below hits an /api/admin/*
// endpoint that independently checks staff status server-side, so
// this whole module simply does nothing useful for a non-staff user
// even if they somehow reach the page)
// ------------------------------------------------------------

const GAME_LABELS = { bomb: "💣 Boom Game", number: "🔢 Number Game" };

function setupAdminPanel() {
  const btn = document.getElementById("open-admin-panel");
  if (btn) btn.addEventListener("click", () => goToPage("admin"));

  document.querySelectorAll(".admin-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".admin-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".admin-panel-section").forEach((s) => s.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("admin-" + tab.dataset.adminTab).classList.add("active");
    });
  });

  document.getElementById("admin-user-search-btn").addEventListener("click", adminSearchUsers);
  document.getElementById("admin-user-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") adminSearchUsers();
  });

  document.querySelectorAll(".admin-export-link").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      downloadAdminExport(a.dataset.export);
    });
  });

  document.getElementById("admin-pin-cancel").addEventListener("click", () => {
    document.getElementById("admin-pin-overlay").style.display = "none";
    goToPage("profile"); // no PIN, no panel -- don't leave them stuck on a half-loaded page
  });

  document.getElementById("admin-pin-submit").addEventListener("click", submitAdminPin);
  document.getElementById("admin-pin-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitAdminPin();
  });

  // Manual lock -- e.g. before setting the phone down. Clears the PIN
  // session immediately client-side (it also naturally expires after
  // 30 minutes server-side regardless).
  document.getElementById("admin-lock-btn").addEventListener("click", () => {
    adminPinToken = null;
    goToPage("profile");
  });
}

async function submitAdminPin() {
  const pin = document.getElementById("admin-pin-input").value.trim();
  const errEl = document.getElementById("admin-pin-error");
  if (!pin) return;
  try {
    const r = await apiFetch("/admin/verify-pin", { method: "POST", json: { pin } });
    adminPinToken = r.token;
    document.getElementById("admin-pin-overlay").style.display = "none";
    document.getElementById("admin-pin-input").value = "";
    errEl.textContent = "";
    await loadAdminPanel();
  } catch (e) {
    errEl.textContent = "❌ " + e.message;
    haptic("error");
  }
}

function promptForAdminPin() {
  document.getElementById("admin-pin-error").textContent = "";
  document.getElementById("admin-pin-input").value = "";
  document.getElementById("admin-pin-overlay").style.display = "flex";
}

// Every individual admin action hits this on failure -- if the PIN
// session simply expired mid-use (30 min TTL), re-prompt right there
// instead of just showing a raw "unauthorized" error.
function describeAdminError(e) {
  if (e.pinRequired) {
    promptForAdminPin();
    return "🔒 PIN ጊዜው አልቋል -- እንደገና ያስገቡ";
  }
  return "❌ " + e.message;
}

async function loadAdminPanel() {
  // Check whether a PIN is even required before doing anything else
  // -- if ADMIN_PANEL_PIN isn't configured server-side, skip straight
  // to loading (keeps the panel usable with zero setup, same as
  // before this feature existed).
  try {
    const status = await apiFetch("/admin/pin-status");
    if (status.pin_required && !adminPinToken) {
      promptForAdminPin();
      return;
    }
  } catch (e) {
    // If even the status check fails, fall through and let the
    // individual panel calls surface the real error.
  }

  try {
    await Promise.all([
      loadAdminStats(),
      loadAdminDepositBonus(),
      loadAdminAll16GameControls(),
      loadAdminSupportTickets(),
      loadAdminMarketplace(),
      loadAdminLogs(),
    ]);
  } catch (e) {
    if (e.pinRequired) {
      promptForAdminPin();
    }
  }
}

async function downloadAdminExport(kind) {
  try {
    const res = await fetch(API_BASE + `/admin/export/${kind}.csv`, {
      headers: {
        "X-Telegram-Init-Data": tg.initData,
        ...(adminPinToken ? { "X-Admin-Pin-Token": adminPinToken } : {}),
      },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      if (body.pin_required) { promptForAdminPin(); return; }
      throw new Error(body.error || "export failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${kind}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    if (e.pinRequired) { promptForAdminPin(); return; }
    alert("❌ " + e.message);
  }
}

async function loadAdminStats() {
  const grid = document.getElementById("admin-stats-grid");
  grid.innerHTML = `<div class="skeleton-line" style="width:100%"></div>`;
  try {
    const s = await apiFetch("/admin/stats");
    grid.innerHTML = `
      <div class="admin-stat-card"><span>👥 Users</span><strong>${s.total_users}</strong></div>
      <div class="admin-stat-card"><span>💰 Total Liability</span><strong>${s.total_liability.toFixed(2)} ብር</strong></div>
      <div class="admin-stat-card"><span>💳 Pending Deposits</span><strong>${s.pending_deposits}</strong></div>
      <div class="admin-stat-card"><span>💸 Pending Withdrawals</span><strong>${s.pending_withdrawals}</strong></div>
      <div class="admin-stat-card"><span>🔒 Pending Escrow</span><strong>${s.pending_escrow_count} (${s.pending_escrow_amount.toFixed(2)} ብር)</strong></div>
      <div class="admin-stat-card"><span>🚩 Open Reports</span><strong>${s.open_reports}</strong></div>
      <div class="admin-stat-card"><span>⛔ Banned Users</span><strong>${s.banned_users}</strong></div>
    `;
  } catch (e) {
    grid.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

async function loadAdminDepositBonus() {
  const settingsEl=document.getElementById("admin-deposit-bonus-settings"), reportEl=document.getElementById("admin-deposit-bonus-report"); if(!settingsEl||!reportEl)return;
  try { const data=await apiFetch("/admin/deposit-bonus"), s=data.settings;
    settingsEl.innerHTML=`<div class="admin-game-card"><label><input type="checkbox" id="deposit-bonus-enabled" ${s.enabled?"checked":""}> Bonus ንቁ ነው</label><label>Bonus (%)</label><input id="deposit-bonus-percent" type="number" min="0" max="100" step="0.1" value="${s.bonus_percent}"><label>Delay (hours)</label><input id="deposit-bonus-delay" type="number" min="0" max="168" step="0.5" value="${s.delay_hours}"><label>Minimum Deposit (ብር)</label><input id="deposit-bonus-min" type="number" min="0" step="0.01" value="${s.min_deposit}"><label>Maximum Bonus (ብር)</label><input id="deposit-bonus-max" type="number" min="0" step="0.01" value="${s.max_bonus}"><button id="save-deposit-bonus" class="admin-save-game">💾 Bonus Settings አስቀምጥ</button><small id="deposit-bonus-status"></small></div>`;
    document.getElementById("save-deposit-bonus").onclick=async()=>{const out=document.getElementById("deposit-bonus-status");try{await apiFetch("/admin/deposit-bonus",{method:"POST",json:{enabled:document.getElementById("deposit-bonus-enabled").checked,bonus_percent:parseFloat(document.getElementById("deposit-bonus-percent").value),delay_hours:parseFloat(document.getElementById("deposit-bonus-delay").value),min_deposit:parseFloat(document.getElementById("deposit-bonus-min").value),max_bonus:parseFloat(document.getElementById("deposit-bonus-max").value)}});out.textContent="✅ Saved";await loadAdminDepositBonus()}catch(e){out.textContent="❌ "+e.message}};
    const rows=data.items||[]; reportEl.innerHTML=`<h4>📊 Bonus Report — ${data.credited_count} credited / ${Number(data.credited_total).toFixed(2)} ብር</h4>`+(rows.length?`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>User</th><th>Deposit</th><th>Bonus</th><th>Eligible</th><th>Credited</th><th>Status</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escapeHtml(r.first_name||r.username||String(r.user_id))}</td><td>${Number(r.deposit_amount).toFixed(2)}</td><td>${Number(r.bonus_amount).toFixed(2)}</td><td>${escapeHtml(r.eligible_at||"")}</td><td>${escapeHtml(r.credited_at||"—")}</td><td>${escapeHtml(r.status)}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty-state">No deposit bonuses yet.</div>`);
  } catch(e){settingsEl.innerHTML=`<div class="empty-state">❌ ${e.message}</div>`}
}

// ---- Admin: welcome bonus / ONE min bet / ONE house edge for all games / high-stakes cashback ----
async function renderPlatformControlsCard(container){
  const card=document.createElement("div"); card.className="admin-game-card"; card.style.marginBottom="12px";
  let d; try{ d=await apiFetch("/admin/platform-controls"); }catch(e){ card.innerHTML=`<div class="empty-state">❌ ${describeAdminError(e)}</div>`; container.appendChild(card); return; }
  const c=d.controls||{}; const chk=(id,v)=>`<input id="pc-${id}" type="checkbox" ${v?"checked":""}>`; const num=(id,v,st="0.01")=>`<input id="pc-${id}" type="number" min="0" step="${st}" value="${v}">`;
  card.innerHTML=`<div class="admin-game-title">⚙️ ዓለም አቀፍ ቅንብር (ሁሉንም ጌም ይመለከታል)</div>
    <div class="admin-note">ይህ ቅንብር ከእያንዳንዱ ጌም የራሱ ቅንብር በላይ ይሠራል። ሲቀይሩ በቀጣዩ ውርርድ ወዲያውኑ ተፈጻሚ ይሆናል።</div>
    <b>🎁 አዲስ ተጠቃሚ ቦነስ</b> <small>(ከዚህ በኋላ ለሚቀላቀሉ፤ አንድ ጊዜ)</small>
    <label>ተግባራዊ ይሁን ${chk("w-on",c.welcome_bonus_enabled)}</label>
    <label>መጠን (ብር)</label>${num("w-amt",c.welcome_bonus_amount)}
    <label>ለመጫወት ብቻ (ያሸነፉት ብቻ ይወጣል) ${chk("w-lock",c.welcome_bonus_locked)}</label>
    <label>የመጀመሪያ ገንዘብ ካስገቡ በኋላ ብቻ ይሰጥ (አካውንት ማባዛት መከላከያ) ${chk("w-dep",c.welcome_bonus_requires_deposit)}</label>
    <label>ለቦነሱ ዝቅተኛ የመጀመሪያ ገንዘብ ማስገባት (ብር)</label>${num("w-mindep",c.welcome_bonus_min_deposit)}
    <small>እስካሁን የተሰጠ: ${d.welcome_given?.players||0} ሰው / ${d.welcome_given?.total||0} ብር</small><hr>
    <b>👥 የ Invite ቦነስ</b>
    <label>ለጋባዡ የሚከፈለው የተጋበዘው ሰው የመጀመሪያ ገንዘብ ካስገባ በኋላ ብቻ ${chk("i-dep",c.invite_bonus_requires_deposit)}</label>
    <label>ዝቅተኛ የመጀመሪያ ገንዘብ (ብር)</label>${num("i-mindep",c.invite_bonus_min_deposit)}<hr>
    <b>🔔 የባለቤት ማስጠንቀቂያ (Telegram)</b> <small>(ቦነስ + Cashback ከቤቱ ትርፍ ከተወሰነ % ሲያልፍ ወይም ትርፉ አሉታዊ ሲሆን)</small>
    <label>ማስጠንቀቂያ ይሠራ ${chk("a-on",c.cost_alert_enabled)}</label>
    <label>ከትርፍ የሚበልጥ % (ለምሳሌ 50)</label>${num("a-pct",c.cost_alert_bonus_pct,"1")}
    <label>ቢያንስ የተሰጠ ቦነስ (ብር)</label>${num("a-min",c.cost_alert_min_bonus)}
    <label>የሚታይበት ጊዜ (ቀን)</label>${num("a-days",c.cost_alert_window_days,"1")}<hr>
    <b>🎯 ዝቅተኛ ውርርድ (Min Bet) — ለሁሉም ጌም</b>
    <label>ተግባራዊ ይሁን ${chk("m-on",c.global_min_bet_enabled)}</label>
    <label>Min Bet (ብር)</label>${num("m-val",c.global_min_bet)}<hr>
    <b>🏠 House Edge — ለሁሉም ጌም (ስፖርት/Boom/Number rake ጭምር)</b>
    <label>ተግባራዊ ይሁን ${chk("e-on",c.global_house_edge_enabled)}</label>
    <label>House Edge (%)</label>${num("e-val",(c.global_house_edge*100).toFixed(2),"0.1")}<hr>
    <b>💸 ከፍተኛ ያስያዙ ተጫዋቾች Cashback</b>
    <label>ተግባራዊ ይሁን ${chk("c-on",c.cashback_enabled)}</label>
    <label>አይነት</label><select id="pc-c-mode"><option value="percent_loss">% ከተሸነፉት</option><option value="percent_wager">% ከተወራረዱት</option><option value="fixed">ቋሚ መጠን</option></select>
    <label>መቶኛ (%)</label>${num("c-pct",c.cashback_percent,"0.1")}
    <label>ቋሚ መጠን (ብር)</label>${num("c-fix",c.cashback_fixed_amount)}
    <label>ለመብቃት ዝቅተኛ ውርርድ ድምር (ብር)</label>${num("c-min",c.cashback_min_wager)}
    <label>ከፍተኛ ለአንድ ሰው (0 = ገደብ የለም)</label>${num("c-max",c.cashback_max_per_player)}
    <label>ጊዜ (ቀን) — የመጀመሪያ ዙር</label>${num("c-days",c.cashback_period_days,"0.5")}
    <label>ለመጫወት ብቻ ${chk("c-lock",c.cashback_locked)}</label>
    <b>🏅 VIP ደረጃዎች</b> <small>(ሲበራ መቶኛው ከተጫዋቹ ደረጃ ይመጣል፤ "ቋሚ መጠን" አይነት ደረጃ አይጠቀምም)</small>
    <label>ደረጃዎች ይሠሩ ${chk("t-on",c.cashback_tiers_enabled)}</label>
    <label>በአንድ መስመር አንድ ደረጃ፦ ስም, ዝቅተኛ ውርርድ, መቶኛ</label>
    <textarea id="pc-t-list" rows="4" style="width:100%">${(c.cashback_tiers||[]).map(t=>`${t.name}, ${t.min_wager}, ${t.percent}`).join("\n")}</textarea>
    <div class="admin-actions"><button class="btn btn-secondary" id="pc-c-preview">👀 ማን ያገኛል</button> <button class="btn btn-primary" id="pc-c-run">✅ Cashback ክፈል</button></div>
    <label>ለአንድ ሰው በእጅ — User ID</label><input id="pc-g-uid" type="number" min="1" step="1">
    <label>መጠን (ብር)</label>${num("g-amt","")}
    <button class="btn btn-secondary" id="pc-g-go">🎁 ስጥ</button>
    <div id="pc-c-out" class="admin-note"></div>
    <button class="btn btn-primary u-save" id="pc-save">💾 አስቀምጥ</button> <span id="pc-status"></span>`;
  container.appendChild(card);
  const $=(id)=>card.querySelector("#pc-"+id); $("c-mode").value=c.cashback_mode||"percent_loss";
  const st=(t)=>{$("status").textContent=t;}; const out=(t)=>{$("c-out").innerHTML=t;};
  $("save").addEventListener("click",async()=>{
    const tiers=($("t-list").value||"").split("\n").map(l=>l.trim()).filter(Boolean).map(l=>{const p=l.split(",").map(x=>x.trim());return {name:p[0],min_wager:Number(p[1]),percent:Number(p[2])};});
    const payload={cashback_tiers_enabled:$("t-on").checked,...(tiers.length?{cashback_tiers:tiers}:{}),welcome_bonus_enabled:$("w-on").checked,welcome_bonus_amount:Number($("w-amt").value),welcome_bonus_locked:$("w-lock").checked,welcome_bonus_requires_deposit:$("w-dep").checked,welcome_bonus_min_deposit:Number($("w-mindep").value),
      invite_bonus_requires_deposit:$("i-dep").checked,invite_bonus_min_deposit:Number($("i-mindep").value),
      cost_alert_enabled:$("a-on").checked,cost_alert_bonus_pct:Number($("a-pct").value),cost_alert_min_bonus:Number($("a-min").value),cost_alert_window_days:Number($("a-days").value),
      global_min_bet_enabled:$("m-on").checked,global_min_bet:Number($("m-val").value),
      global_house_edge_enabled:$("e-on").checked,global_house_edge_percent:Number($("e-val").value),
      cashback_enabled:$("c-on").checked,cashback_mode:$("c-mode").value,cashback_percent:Number($("c-pct").value),cashback_fixed_amount:Number($("c-fix").value),
      cashback_min_wager:Number($("c-min").value),cashback_max_per_player:Number($("c-max").value),cashback_period_days:Number($("c-days").value),cashback_locked:$("c-lock").checked};
    try{await apiFetch("/admin/platform-controls",{method:"POST",json:payload});st("✅ ተቀምጧል — ወዲያውኑ ተፈጻሚ ሆኗል");haptic("success");setTimeout(()=>loadAdminAll16GameControls(),900);}catch(e){st(describeAdminError(e));haptic("error");}
  });
  $("c-preview").addEventListener("click",async()=>{
    try{const r=await apiFetch("/admin/cashback/preview");
      out(`${r.players} ሰው — ጠቅላላ ${r.total} ብር (${r.period_start} → ${r.period_end})<br>`+(r.items||[]).slice(0,20).map(i=>`#${i.user_id}${i.tier?` [${i.tier}]`:""}: ውርርድ ${i.staked} / ኪሳራ ${i.net_loss} → <b>${i.cashback}</b>`).join("<br>"));}catch(e){out(describeAdminError(e));}
  });
  $("c-run").addEventListener("click",async()=>{
    if(!confirm("Cashback ለሁሉም ብቁ ተጫዋቾች ይከፈላል። መጀመሪያ 'አስቀምጥ' ተጭነዋል? ይቀጥሉ?"))return;
    try{const r=await apiFetch("/admin/cashback/run",{method:"POST",json:{}});out(`✅ ${r.players} ሰው ተከፍሏል — ጠቅላላ ${r.total_paid} ብር`);haptic("success");}catch(e){out(describeAdminError(e));haptic("error");}
  });
  $("g-go").addEventListener("click",async()=>{
    try{const r=await apiFetch("/admin/cashback/grant",{method:"POST",json:{user_id:Number($("g-uid").value),amount:Number($("g-amt").value)}});out(`✅ #${r.user_id} ← ${r.amount} ብር`);haptic("success");}catch(e){out(describeAdminError(e));haptic("error");}
  });
}

// ---- Admin: one-page bonus / cashback cost report ----
async function renderBonusReportCard(container){
  const card=document.createElement("div"); card.className="admin-game-card"; card.style.marginBottom="12px";
  card.innerHTML=`<div class="admin-game-title">📊 የቦነስ እና Cashback ወጪ ሪፖርት</div>
    <label>ጊዜ</label><select id="br-days"><option value="7">7 ቀን</option><option value="30" selected>30 ቀን</option><option value="90">90 ቀን</option><option value="0">ሁሉም ጊዜ</option></select>
    <div id="br-out" class="admin-note">…</div>`;
  container.appendChild(card);
  const out=card.querySelector("#br-out"), sel=card.querySelector("#br-days"); const esc=(v)=>String(v??"").replace(/[&<>"]/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
  const labels={welcome:"🎁 Welcome",invite:"👥 Invite",mystery_box:"📦 Mystery box",deposit_bonus:"💰 Deposit bonus",cashback:"💸 Cashback"};
  async function load(){
    out.textContent="…";
    try{
      const r=await apiFetch("/admin/bonus-report?days="+sel.value);
      const given=Object.entries(r.bonus_given||{}).map(([k,v])=>`${labels[k]||esc(k)}: <b>${v.total}</b> ብር (${v.count})`).join("<br>");
      const games=(r.games||[]).slice(0,15).map(g=>`${esc(g.game)}: ውርርድ ${g.staked} → ትርፍ <b>${g.house_profit}</b>${g.hold_pct==null?"":` (${g.hold_pct}%)`}`).join("<br>")||"ምንም ውርርድ የለም";
      const warn=(r.warnings||[]).map(w=>`<div style="color:#e5484d">⚠️ ${esc(w)}</div>`).join("");
      out.innerHTML=`${warn}<b>የተሰጠ ቦነስ ጠቅላላ: ${r.bonus_given_total} ብር</b><br>${given}<hr>
        በተጫዋቾች እጅ ያልተጠቀሙበት ቦነስ: <b>${r.outstanding?.locked_bonus_in_wallets}</b> ብር (${r.outstanding?.players} ሰው)<hr>
        የቤቱ ትርፍ: <b>${r.house_profit_total}</b> ብር<br>ቦነስ ከትርፍ የበላው: <b>${r.bonus_cost_pct_of_house_profit==null?"—":r.bonus_cost_pct_of_house_profit+"%"}</b><br>ከቦነስ በኋላ ንጹህ: <b>${r.net_after_bonus}</b> ብር<hr>${games}`;
    }catch(e){out.innerHTML=describeAdminError(e);}
  }
  sel.addEventListener("change",load); load();
}

// Show a stored fraction as a percent WITHOUT rounding it to 1 decimal -- otherwise saving any other field on the
// card silently rewrites the real house edge (e.g. 8.25% -> 8.3%).
function adminPct(frac){ return String(Number((Number(frac||0)*100).toFixed(4))); }

async function loadAdminAll16GameControls() {
  const container = document.getElementById("admin-game-cards");
  if (!container) return;
  container.innerHTML = `<div class="skeleton-card"><div class="skeleton-line" style="width:70%"></div></div>`;
  try {
    const data = await apiFetch("/admin/game-control");
    const items = data.items || [];
    container.innerHTML = `<div class="admin-note" style="margin-bottom:10px">👑 ${items.filter((x)=>x.key!=="sports"&&x.key!=="marketplace").length} Games — Admin ብቻ ነው የGame ON/OFF፣ ገቢ/House Result፣ መግቢያ (Entry Fee ወይም Min/Max Bet)፣ RTP/House Edge እና Marketplace commission የሚቆጣጠረው። ሁሉም ጨዋታ ላይ ተፈጻሚ ይሆናል። የPlayer ውጤት በserver ላይ ብቻ ይወሰናል።</div>`;
    await renderPlatformControlsCard(container);
    await renderBonusReportCard(container);
    for (const s of items) {
      const card=document.createElement("div"); card.className="admin-game-card";
      const st=s.stats||{};
      let controls="";
      if (s.key==="bomb"||s.key==="number") {
        controls=`<label>Entry Fee (ብር)</label><input class="u-entry" type="number" min="0.01" step="0.01" value="${Number(s.entry_fee).toFixed(2)}">\n<label>House Edge (%)</label><input class="u-edge" type="number" min="0" max="30" step="0.1" value="${adminPct(s.house_edge)}">`;
      } else if (s.key!=="sports"&&s.key!=="marketplace") {
        controls=`<label>Min Bet — መግቢያ (ብር)</label><input class="u-min" type="number" min="0.01" step="0.01" value="${Number(s.min_stake).toFixed(2)}">\n<label>Max Bet (ብር)</label><input class="u-max" type="number" min="0.01" step="0.01" value="${Number(s.max_stake).toFixed(2)}">\n<label>House Edge / RTP</label><input class="u-edge" type="number" min="0" max="30" step="0.1" value="${adminPct(s.house_edge)}">`;
        if(s.key==="wheel") controls += `<div class="wheel-prize-admin"><b>🎡 10 Wheel Prizes ×</b><div class="wheel-prize-grid">${(s.wheel_prizes||[]).map((v,i)=>`<label>S${i+1}<input class="u-prize" data-i="${i}" type="number" min="0" max="1000" step="0.01" value="${Number(v).toFixed(2)}"></label>`).join("")}</div></div>`;
      } else if (s.key==="marketplace") {
        controls=`<label>Admin Commission (%)</label><input class="u-commission" type="number" min="0" max="95" step="0.1" value="${Number(s.commission_percent||0).toFixed(1)}">`;
      } else {
        controls=`<div class="admin-note">Match/odds/result በSports Admin ውስጥ ይቆጣጠራሉ።</div>`;
      }
      const ovr=[]; if(s.entry_overridden) ovr.push(`Entry Fee → ${Number(s.effective_entry_fee).toFixed(2)} ብር`); if(s.min_overridden) ovr.push(`Min Bet → ${Number(s.effective_min_stake).toFixed(2)} ብር`); if(s.edge_overridden) ovr.push(`House Edge → ${adminPct(s.effective_house_edge)}%`);
      if(ovr.length) controls+=`<div class="admin-note" style="color:#e5a000">🔒 ዓለም አቀፍ ቅንብር ይህን ጌም እየሻረው ነው፤ ተጫዋቹ የሚያየው፦ ${ovr.join(" · ")}። ከላይ ያለው ዋጋ የሚሠራው ዓለም አቀፉን (⚙️) ሲያጠፉት ነው።</div>`;
      card.innerHTML=`<div class="admin-game-title">${s.name} ${s.enabled?"":"<span class=\"admin-disabled-tag\">ጠፍቷል</span>"}</div>${controls}<div class="admin-computed-win">${s.key==="marketplace"?`💰 Commission Revenue: <strong>${Number(s.revenue||0).toFixed(2)} ብር</strong>`:s.key==="sports"?`⚽ Sports ማስተዳደር: <strong>Matches / Odds / Settlement</strong>`:`📊 Rounds ${st.rounds||0} · Collected ${Number(st.staked||0).toFixed(2)} · Paid ${Number(st.paid||0).toFixed(2)} · House Result ${Number(st.house_result||0).toFixed(2)} ብር`}</div><label class="admin-toggle-row"><input class="u-enabled" type="checkbox" ${s.enabled?"checked":""}> Game ON</label><button class="admin-save-game u-save">💾 አስቀምጥ</button><small class="admin-game-status u-status"></small>`;
      card.querySelector(".u-save").addEventListener("click",async()=>{
        const payload={key:s.key,enabled:card.querySelector(".u-enabled").checked};
        if(s.key==="bomb"||s.key==="number"){payload.entry_fee=Number(card.querySelector(".u-entry").value);payload.house_edge=Number(card.querySelector(".u-edge").value)/100;}
        else if(s.key!=="sports"&&s.key!=="marketplace"){payload.min_stake=Number(card.querySelector(".u-min").value);payload.max_stake=Number(card.querySelector(".u-max").value);payload.house_edge=Number(card.querySelector(".u-edge").value)/100;if(s.key==="wheel")payload.wheel_prizes=[...card.querySelectorAll(".u-prize")].map(x=>Number(x.value));}
        else if(s.key==="marketplace")payload.commission_percent=Number(card.querySelector(".u-commission").value);
        try{await apiFetch("/admin/game-control",{method:"POST",json:payload});card.querySelector(".u-status").textContent="✅ Saved";haptic("success");setTimeout(()=>loadAdminAll16GameControls(),700);}catch(e){card.querySelector(".u-status").textContent=describeAdminError(e);haptic("error");}
      });
      container.appendChild(card);
    }
  } catch(e){container.innerHTML=`<div class="empty-state">❌ ${e.message}</div>`;}
}

async function loadAdminGameCards() {
  const container = document.getElementById("admin-game-cards");
  container.innerHTML = `<div class="skeleton-card"><div class="skeleton-line" style="width:70%"></div></div>`;
  try {
    const settings = await apiFetch("/admin/games/settings");
    container.innerHTML = "";
    for (const key of ["bomb", "number"]) {
      const s = settings[key];
      const card = document.createElement("div");
      card.className = "admin-game-card";
      card.innerHTML = `
        <div class="admin-game-title">${GAME_LABELS[key]} ${s.enabled ? "" : '<span class="admin-disabled-tag">ጠፍቷል</span>'}</div>
        <label>Entry Fee (ብር)</label>
        <input type="number" class="admin-entry-fee" min="1" step="0.01" value="${s.entry_fee}">
        <label>House Edge (%) -- ይህ ካልቀየሩት በስተቀር አይቀየርም</label>
        <input type="number" class="admin-house-edge" min="0" max="30" step="0.1" value="${(s.house_edge * 100).toFixed(1)}">
        <div class="admin-computed-win">🏆 Win Amount (auto-calculated): <strong>${s.win_amount.toFixed(2)} ብር</strong></div>
        <label class="admin-toggle-row"><input type="checkbox" class="admin-enabled-toggle" ${s.enabled ? "checked" : ""}> ጨዋታው ንቁ ነው</label>
        <button class="admin-save-game">💾 አስቀምጥ</button>
        <small class="admin-game-status"></small>
      `;
      const winEl = card.querySelector(".admin-computed-win strong");
      const entryInput = card.querySelector(".admin-entry-fee");
      const edgeInput = card.querySelector(".admin-house-edge");
      const statusEl = card.querySelector(".admin-game-status");

      // Live preview of what win_amount WILL become, computed the
      // exact same way the server's locked trigger computes it --
      // purely cosmetic (server always recalculates for real on
      // save), so admin sees the effect before committing.
      const winProb = s.win_probability;
      function updatePreview() {
        const entry = parseFloat(entryInput.value) || 0;
        const edge = (parseFloat(edgeInput.value) || 0) / 100;
        const preview = entry * (1 - edge) / winProb;
        winEl.textContent = preview.toFixed(2) + " ብር";
      }
      entryInput.addEventListener("input", updatePreview);
      edgeInput.addEventListener("input", updatePreview);

      card.querySelector(".admin-save-game").addEventListener("click", async () => {
        const entry_fee = parseFloat(entryInput.value);
        const house_edge = parseFloat(edgeInput.value) / 100;
        const enabled = card.querySelector(".admin-enabled-toggle").checked;

        // Sanity guard, not a hard limit -- the backend already
        // enforces the real 0-95% bound. This just makes an admin
        // pause before a value that's very likely a typo: an edge
        // this low can lose the house money on every round played;
        // one this high makes the game not worth playing.
        const edgePercent = house_edge * 100;
        if (edgePercent < 10 || edgePercent > 70) {
          const proceed = confirm(
            `⚠️ House Edge ${edgePercent.toFixed(1)}% ያልተለመደ ነው (የተለመደው ክልል 10%-70%)። ` +
            `${edgePercent < 10 ? "ይህ ጨዋታው ገንዘብ እንዲያጣ ሊያደርግ ይችላል።" : "ይህ ጨዋታውን ላለመጫወት የሚያደርግ ሊሆን ይችላል።"} ` +
            `በርግጥ መቀጠል ይፈልጋሉ?`
          );
          if (!proceed) return;
        }

        try {
          const r = await apiFetch("/admin/games/settings", {
            method: "POST", json: { key, entry_fee, house_edge, enabled }
          });
          winEl.textContent = r.win_amount.toFixed(2) + " ብር";
          statusEl.textContent = "✅ ተቀምጧል";
          haptic("success");
          setTimeout(() => { statusEl.textContent = ""; }, 2000);
        } catch (e) {
          statusEl.textContent = describeAdminError(e);
          haptic("error");
        }
      });

      container.appendChild(card);
    }
  } catch (e) {
    container.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

async function loadAdminCabinetGameCards() {
  const container = document.getElementById("admin-cabinet-game-cards");
  if (!container) return;
  const labels = {
    dice:"🎲 Dice", slot:"🎰 Slot", wheel:"🎡 Wheel", keno:"🎯 Keno",
    chicken:"🐔 Chicken", aviator:"✈️ Aviator", plinko:"🟣 Plinko", mines:"💣 Mines",
    jet:"🚀 Jet", fish:"🐟 Fish", rabbit:"🐇 Rabbit (retired)", penaltystreak:"⚽ Penalty Streak", tower:"💣 Boom Ladder", chicken2:"🐔 Chicken Road 2", baccarat:"🎴 Baccarat", blackjack:"🃏 Blackjack", card:"🃏 Card", coinflip:"🪙 Coin Flip", penalty:"⚽ Penalty"
  };
  container.innerHTML = `<div class="skeleton-card"><div class="skeleton-line" style="width:70%"></div></div>`;
  try {
    const data = await apiFetch("/admin/cabinet-games/settings");
    container.innerHTML = "";
    for (const s of data.items || []) {
      const card = document.createElement("div");
      card.className = "admin-game-card";
      const edgePct = Number(s.house_edge || 0) * 100;
      const rtpPct = Number(s.rtp || (1 - Number(s.house_edge || 0))) * 100;
      card.innerHTML = `
        <div class="admin-game-title">${labels[s.game_key] || s.label || s.game_key} ${s.enabled ? "" : '<span class="admin-disabled-tag">ጠፍቷል</span>'}</div>
        <label>Min Bet (ብር)</label>
        <input type="number" class="cab-min" min="0.01" step="0.01" value="${s.min_stake}">
        <label>Max Bet (ብር)</label>
        <input type="number" class="cab-max" min="0.01" step="0.01" value="${s.max_stake}">
        <label>House Edge (%)</label>
        <input type="number" class="cab-edge" min="0" max="95" step="0.1" value="${edgePct.toFixed(1)}">
        ${s.game_key === "wheel" ? `<div class="wheel-prize-admin"><b>🎡 Wheel Sector Prizes (×)</b><small>10 sectors — እያንዳንዱ sector ላይ የሚከፈለውን multiplier ያስገቡ። ሁሉም sectors እኩል ዕድል አላቸው።</small><div class="wheel-prize-grid">${(s.wheel_prizes || [0,0,0.5,1,1.2,1.5,2,3,5,10]).map((v,i)=>`<label>S${i+1}<input type="number" class="wheel-prize" data-sector="${i+1}" min="0" max="1000" step="0.01" value="${Number(v).toFixed(2)}"></label>`).join("")}</div></div>` : ""}
        <div class="admin-computed-win">📊 RTP: <strong class="cab-rtp">${rtpPct.toFixed(1)}%</strong></div>
        <label class="admin-toggle-row"><input type="checkbox" class="cab-enabled" ${s.enabled ? "checked" : ""}> Game ON</label>
        <button class="admin-save-game cab-save">💾 አስቀምጥ</button>
        <small class="admin-game-status cab-status"></small>`;
      const edge = card.querySelector(".cab-edge");
      const rtp = card.querySelector(".cab-rtp");
      const status = card.querySelector(".cab-status");
      edge.addEventListener("input", () => {
        const e = Math.max(0, Math.min(95, Number(edge.value) || 0));
        rtp.textContent = (100 - e).toFixed(1) + "%";
      });
      card.querySelector(".cab-save").addEventListener("click", async () => {
        const min_stake = Number(card.querySelector(".cab-min").value);
        const max_stake = Number(card.querySelector(".cab-max").value);
        const house_edge = Number(edge.value) / 100;
        const enabled = card.querySelector(".cab-enabled").checked;
        const wheel_prizes = s.game_key === "wheel" ? [...card.querySelectorAll(".wheel-prize")].map(x => Number(x.value)) : undefined;
        if (s.game_key === "wheel" && (!wheel_prizes || wheel_prizes.length !== 10 || wheel_prizes.some(x => !Number.isFinite(x) || x < 0 || x > 1000))) { status.textContent = "❌ 10 Wheel prizes በትክክል ያስገቡ"; return; }
        if (!(min_stake > 0) || !(max_stake >= min_stake) || house_edge < 0 || house_edge > 0.95) {
          status.textContent = "❌ የተሳሳተ ዋጋ"; return;
        }
        try {
          const payload = {game_key:s.game_key,min_stake,max_stake,house_edge,enabled};
          if (s.game_key === "wheel") payload.wheel_prizes = wheel_prizes;
          await apiFetch("/admin/cabinet-games/settings", {method:"POST", json:payload});
          status.textContent = `✅ Saved — HE ${(house_edge*100).toFixed(1)}% / RTP ${((1-house_edge)*100).toFixed(1)}%`;
          haptic("success");
        } catch (e) { status.textContent = describeAdminError(e); haptic("error"); }
      });
      container.appendChild(card);
    }
  } catch (e) {
    container.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

async function loadAdminMarketplace() {
  const escrowList = document.getElementById("admin-escrow-list");
  const reportsList = document.getElementById("admin-reports-list");
  const moderationList = document.getElementById("admin-marketplace-moderation-list");
  const statsEl = document.getElementById("admin-marketplace-stats");
  if (escrowList) escrowList.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  if (reportsList) reportsList.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  if (moderationList) moderationList.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;

  const filter = document.getElementById("admin-mkt-status-filter");
  const status = filter ? filter.value : "pending";
  try {
    const data = await apiFetch(`/admin/marketplace/moderation?status=${encodeURIComponent(status)}`);
    if (statsEl) statsEl.innerHTML = `
      <div class="admin-stat-card"><span>⏳ Pending Posts</span><strong>${data.stats.pending_posts}</strong></div>
      <div class="admin-stat-card"><span>🚩 Open Reports</span><strong>${data.stats.open_reports}</strong></div>
      <div class="admin-stat-card"><span>🔒 Active Escrow</span><strong>${data.stats.active_disputes}</strong></div>
      <div class="admin-stat-card"><span>🚫 Suspended Creators</span><strong>${data.stats.suspended_creators}</strong></div>
      <div class="admin-stat-card" id="admin-mkt-commission-card"><span>💼 Marketplace Commission</span><strong>Loading…</strong></div>`;
    try {
      const cs = await apiFetch("/admin/marketplace/commission");
      const c = document.getElementById("admin-mkt-commission-card");
      if (c) c.innerHTML = `<span>💼 Marketplace Commission</span><strong>${Number(cs.commission_percent).toFixed(1)}%</strong><input id="admin-mkt-commission-input" type="number" min="0" max="95" step="0.1" value="${Number(cs.commission_percent).toFixed(1)}" style="width:90px"><button id="admin-mkt-commission-save">💾 Save</button><small id="admin-mkt-commission-status"></small>`;
      const save = document.getElementById("admin-mkt-commission-save");
      if (save) save.onclick = async () => {
        const input=document.getElementById("admin-mkt-commission-input"), status=document.getElementById("admin-mkt-commission-status");
        const percent=Number(input.value);
        if (!Number.isFinite(percent) || percent<0 || percent>95) { status.textContent="❌ 0–95% ውስጥ ያስገቡ"; return; }
        try { const r=await apiFetch("/admin/marketplace/commission",{method:"POST",json:{commission_percent:percent}}); status.textContent=`✅ ${Number(r.commission_percent).toFixed(1)}% saved`; haptic("success"); } catch(e){ status.textContent=describeAdminError(e); haptic("error"); }
      };
    } catch(e) { const c=document.getElementById("admin-mkt-commission-card"); if(c)c.innerHTML=`<span>💼 Marketplace Commission</span><strong>❌ ${escapeHtml(e.message)}</strong>`; }
    if (moderationList) {
      moderationList.innerHTML = "";
      if (!data.posts.length) moderationList.innerHTML = `<div class="empty-state">🎉 የሚመረመር post የለም</div>`;
      for (const p of data.posts) {
        const card=document.createElement("div"); card.className="admin-list-card";
        const creator=`${escapeHtml(p.creator_first_name||p.creator_username||p.creator_id||"Creator")} (#${p.creator_id})`;
        let media=[]; try{media=p.media_items||[]}catch(e){}
        const mediaHtml=media.length ? media.map((m,i)=>`<div style="margin:5px 0">🎞️ Media ${i+1} — ${escapeHtml(m.media_type||"")} ${m.moderation_status?`[${escapeHtml(m.moderation_status)}]`:""} ${m.moderation_removed?"[REMOVED]":""}<br><button data-mi="${i}" data-ma="approve">Approve</button> <button data-mi="${i}" data-ma="reject">Reject</button> <button data-mi="${i}" data-ma="remove">Remove</button></div>`).join("") : `<small>Media: none</small>`;
        card.innerHTML=`
          <div><strong>#${p.post_id} ${escapeHtml(p.title||"")}</strong> — ${Number(p.price||0).toFixed(2)} ብር</div>
          <small>Creator: ${creator} | Status: <b>${escapeHtml(p.moderation_status||"pending")}</b> | Price: ${escapeHtml(p.price_status||"pending")} | Media: ${escapeHtml(p.media_status||"pending")}</small>
          <small>${escapeHtml(p.category||"General")} · ${escapeHtml(p.service_type||"")} · ${escapeHtml(p.duration_minutes==null?"":String(p.duration_minutes))} min</small>
          <div style="margin:7px 0">${escapeHtml(p.description||"")}</div>
          <div class="admin-btn-row">
            <button data-action="approve">✅ Approve Post</button><button data-action="reject">❌ Reject</button><button data-action="hide">🙈 Hide</button><button data-action="delete">🗑️ Delete</button><button data-action="restore">♻️ Restore</button>
          </div>
          <div class="admin-btn-row"><button data-action="price_approve">💰 Approve Price</button><button data-action="price_reject">🚫 Reject Price</button><button data-creator-action="verify">✅ Verify Creator</button><button data-creator-action="unverify">Unverify</button><button data-creator-action="suspend">⛔ Suspend</button><button data-creator-action="unsuspend">Unsuspend</button><button data-creator-action="ban">🚫 Ban</button></div>
          <div class="admin-media-review">${mediaHtml}</div><small class="admin-moderation-status"></small>`;
        const st=card.querySelector(".admin-moderation-status");
        const moderate=async(action)=>{const reason=prompt(`Reason / note for ${action}:`,""); if(reason===null)return; try{await apiFetch(`/admin/marketplace/posts/${p.post_id}/moderate`,{method:"POST",json:{action,reason,note:reason}}); st.textContent=`✅ ${action} saved`; haptic("success"); loadAdminMarketplace();}catch(e){st.textContent=describeAdminError(e);haptic("error");}};
        card.querySelectorAll("button[data-action]").forEach(b=>b.addEventListener("click",()=>moderate(b.dataset.action)));
        card.querySelectorAll("button[data-creator-action]").forEach(b=>b.addEventListener("click",async()=>{const reason=prompt(`Creator ${b.dataset.creatorAction} reason:`,"");if(reason===null)return;try{await apiFetch(`/admin/marketplace/creators/${p.creator_id}/moderate`,{method:"POST",json:{action:b.dataset.creatorAction,reason}});st.textContent=`✅ creator ${b.dataset.creatorAction} saved`;loadAdminMarketplace();}catch(e){st.textContent=describeAdminError(e);}}));
        card.querySelectorAll("button[data-mi]").forEach(b=>b.addEventListener("click",async()=>{const reason=prompt(`Media ${b.dataset.ma} reason:`,"");if(reason===null)return;try{await apiFetch(`/admin/marketplace/posts/${p.post_id}/media/${b.dataset.mi}/moderate`,{method:"POST",json:{action:b.dataset.ma,reason}});st.textContent=`✅ media ${b.dataset.ma} saved`;loadAdminMarketplace();}catch(e){st.textContent=describeAdminError(e);}}));
        moderationList.appendChild(card);
      }
    }
  } catch(e) { if(moderationList) moderationList.innerHTML=`<div class="empty-state">${describeAdminError(e)}</div>`; }

  try {
    const data = await apiFetch("/admin/marketplace/pending");
    escrowList.innerHTML = data.pending.length ? "" : `<div class="empty-state">🎉 ምንም pending የለም</div>`;
    for (const tx of data.pending) {
      const card=document.createElement("div"); card.className="admin-list-card";
      card.innerHTML=`<div>${escapeHtml(tx.title||"(deleted service)")} — ${Number(tx.amount||0).toFixed(2)} ብር</div><small>Buyer: ${tx.buyer_id} → Creator: ${tx.creator_id} — ${escapeHtml(tx.created_at)}</small><input type="text" class="admin-resolve-note" placeholder="ማስታወሻ"><div class="admin-btn-row"><button class="admin-release-btn">✅ Release</button><button class="admin-refund-btn">↩️ Refund</button></div><small class="admin-tx-status"></small>`;
      const act=async(action)=>{try{const note=card.querySelector(".admin-resolve-note").value.trim();const r=await apiFetch("/marketplace/admin/resolve",{method:"POST",json:{tx_id:tx.tx_id,action,note}});card.querySelector(".admin-tx-status").textContent="✅ "+r.message;card.querySelector(".admin-btn-row").style.display="none";haptic("success");}catch(e){card.querySelector(".admin-tx-status").textContent=describeAdminError(e);haptic("error");}};
      card.querySelector(".admin-release-btn").onclick=()=>act("release"); card.querySelector(".admin-refund-btn").onclick=()=>act("refund"); escrowList.appendChild(card);
    }
  } catch(e){escrowList.innerHTML=`<div class="empty-state">${describeAdminError(e)}</div>`;}

  try {
    const data=await apiFetch("/admin/marketplace/reports"); reportsList.innerHTML=""; const open=data.reports.filter(r=>r.status==="open");
    if(!open.length) reportsList.innerHTML=`<div class="empty-state">🎉 ክፍት ሪፖርት የለም</div>`;
    for(const r of open){const card=document.createElement("div");card.className="admin-list-card";card.innerHTML=`<div>🚩 ${escapeHtml(r.title||"(deleted service)")}</div><small>Reporter: ${r.reporter_id} — Creator: ${r.creator_id} — ${escapeHtml(r.created_at)}</small><div>${escapeHtml(r.reason)}</div><button>✅ Reviewed</button>`;card.querySelector("button").onclick=async()=>{try{await apiFetch("/admin/marketplace/reports/resolve",{method:"POST",json:{report_id:r.report_id}});card.remove();haptic("success");}catch(e){if(e.pinRequired)promptForAdminPin();else alert("❌ "+e.message);}};reportsList.appendChild(card);}
  } catch(e){reportsList.innerHTML=`<div class="empty-state">${describeAdminError(e)}</div>`;}
}

// Marketplace moderation controls are intentionally wired here so the admin
// panel can be refreshed without reopening the Mini App.
setTimeout(()=>{const f=document.getElementById("admin-mkt-status-filter");const b=document.getElementById("admin-mkt-refresh");if(f)f.addEventListener("change",loadAdminMarketplace);if(b)b.addEventListener("click",loadAdminMarketplace);},0);

async function adminSearchUsers() {
  const q = document.getElementById("admin-user-search").value.trim();
  const results = document.getElementById("admin-user-results");
  if (!q) return;
  results.innerHTML = `<div class="skeleton-line" style="width:80%"></div>`;
  try {
    const data = await apiFetch("/admin/users/search?q=" + encodeURIComponent(q));
    results.innerHTML = "";
    if (!data.users.length) {
      results.innerHTML = `<div class="empty-state">ምንም ተጠቃሚ አልተገኘም</div>`;
      return;
    }
    for (const u of data.users) {
      const card = document.createElement("div");
      card.className = "admin-list-card";
      card.innerHTML = `
        <div>👤 ${escapeHtml(u.first_name || "")} (@${escapeHtml(u.username || "-")}) -- ID: ${u.user_id}</div>
        <small>💰 ${u.balance.toFixed(2)} ብር ${u.banned ? '<span class="admin-disabled-tag">የታገደ</span>' : ""} ${u.manager ? "⭐ Staff" : ""}</small>
        ${u.self_excluded_until ? `<small style="color:var(--terracotta)">🛑 እራሱን ያገደው እስከ ${escapeHtml(u.self_excluded_until)} ድረስ ነው (admin ሊሰርዘው አይችልም)</small>` : ""}
        <div class="admin-btn-row">
          <input type="number" class="admin-adjust-amount" placeholder="±መጠን" step="0.01">
          <button class="admin-adjust-btn">🛠️ አስተካክል</button>
        </div>
        <input type="text" class="admin-adjust-reason" placeholder="ምክንያት (ግዴታ)">
        <button class="admin-ban-toggle-btn">${u.banned ? "✅ Unban" : "⛔ Ban"}</button>
        <small class="admin-user-status"></small>
      `;
      const statusEl = card.querySelector(".admin-user-status");
      card.querySelector(".admin-adjust-btn").addEventListener("click", async () => {
        const amount = parseFloat(card.querySelector(".admin-adjust-amount").value);
        const reason = card.querySelector(".admin-adjust-reason").value.trim();
        if (!amount) { statusEl.textContent = "❌ መጠን ያስፈልጋል"; return; }
        if (!reason) { statusEl.textContent = "❌ ምክንያት ያስፈልጋል"; return; }
        try {
          const r = await apiFetch("/admin/users/adjust-balance", { method: "POST", json: { user_id: u.user_id, amount, reason } });
          if (r.confirmation_required) {
            const ok = confirm(
              `⚠️ ይህ ትልቅ ማስተካክያ ነው (${amount > 0 ? "+" : ""}${amount} ብር) -- ማረጋገጫ ያስፈልጋል። ${r.message}\n\nመቀጠል ይፈልጋሉ?`
            );
            if (!ok) { statusEl.textContent = "ተሰርዟል"; return; }
            const r2 = await apiFetch("/admin/users/adjust-balance", {
              method: "POST",
              json: { user_id: u.user_id, amount, reason, confirm_token: r.confirm_token }
            });
            statusEl.textContent = "✅ ተስተካክሏል (ተረጋግጧል)";
            haptic("success");
            return;
          }
          statusEl.textContent = "✅ ተስተካክሏል";
          haptic("success");
        } catch (e) {
          statusEl.textContent = describeAdminError(e);
          haptic("error");
        }
      });
      card.querySelector(".admin-ban-toggle-btn").addEventListener("click", async (e) => {
        const willBan = !u.banned;
        const reason = willBan ? (prompt("የማገጃ ምክንያት፦") || "") : "";
        try {
          await apiFetch("/admin/users/ban", { method: "POST", json: { user_id: u.user_id, banned: willBan, reason } });
          u.banned = willBan;
          e.target.textContent = willBan ? "✅ Unban" : "⛔ Ban";
          statusEl.textContent = "✅ ተከናውኗል";
          haptic("success");
        } catch (err) {
          statusEl.textContent = describeAdminError(err);
        }
      });
      results.appendChild(card);
    }
  } catch (e) {
    results.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

async function loadAdminLogs() {
  const opsGrid = document.getElementById("admin-ops-grid");
  const multiList = document.getElementById("admin-multiaccount-list");
  const reconList = document.getElementById("admin-reconciliation-list");
  const sportsList = document.getElementById("admin-sports-list");
  const actionsList = document.getElementById("admin-actions-list");
  const errorsList = document.getElementById("admin-errors-list");
  opsGrid.innerHTML = multiList.innerHTML = reconList.innerHTML = sportsList.innerHTML = actionsList.innerHTML = errorsList.innerHTML =
    `<div class="skeleton-line" style="width:80%"></div>`;

  try {
    const [backup, summary] = await Promise.all([
      apiFetch("/admin/backups/status"),
      apiFetch("/admin/summary/daily"),
    ]);
    opsGrid.innerHTML = `
      <div class="admin-stat-card">
        <span>🗄️ Latest Backup</span>
        <strong>${backup.latest_backup ? backup.hours_ago + "h ago" : "የለም"}</strong>
        ${backup.warning ? `<small style="color:var(--terracotta)">⚠️ ${backup.warning}</small>` : ""}
      </div>
      <div class="admin-stat-card"><span>💳 Deposits (24h)</span><strong>${summary.deposits.count} (${summary.deposits.total.toFixed(2)} ብር)</strong></div>
      <div class="admin-stat-card"><span>💸 Withdrawals (24h)</span><strong>${summary.withdrawals.count} (${summary.withdrawals.total.toFixed(2)} ብር)</strong></div>
      <div class="admin-stat-card"><span>🎮 Game House Result (24h)</span><strong>${summary.games.house_result.toFixed(2)} ብር</strong></div>
      <div class="admin-stat-card"><span>🛍️ Marketplace Volume (24h)</span><strong>${summary.marketplace.count} (${summary.marketplace.volume.toFixed(2)} ብር)</strong></div>
    `;
  } catch (e) {
    opsGrid.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }

  try {
    const data = await apiFetch("/admin/multi-accounting");
    multiList.innerHTML = "";
    if (!data.flagged.length) {
      multiList.innerHTML = `<div class="empty-state">🎉 ምንም አልተገኘም</div>`;
    }
    for (const f of data.flagged) {
      const div = document.createElement("div");
      div.className = "admin-list-card";
      div.innerHTML = `
        <div>⚠️ አካውንት፦ ${escapeHtml(f.acc_number)}</div>
        <small>${f.distinct_user_count} የተለያዩ users ተጠቅመውበታል፦ ${f.user_ids.join(", ")}</small>
      `;
      multiList.appendChild(div);
    }
  } catch (e) {
    multiList.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }

  try {
    const data = await apiFetch("/admin/reconciliation");
    reconList.innerHTML = "";
    if (!data.mismatches.length) {
      reconList.innerHTML = `<div class="empty-state">🎉 ምንም ልዩነት የለም -- ሁሉም ትክክል ነው</div>`;
    }
    for (const m of data.mismatches) {
      const div = document.createElement("div");
      div.className = "admin-list-card";
      div.innerHTML = `
        <div>⚠️ ${escapeHtml(m.first_name || "User")} (ID: ${m.user_id})</div>
        <small>Balance: ${m.balance.toFixed(2)} ብር -- Transaction Sum: ${m.transaction_sum.toFixed(2)} ብር</small>
        <div class="admin-report-reason">ልዩነት፦ ${m.difference > 0 ? "+" : ""}${m.difference.toFixed(2)} ብር</div>
      `;
      reconList.appendChild(div);
    }
  } catch (e) {
    reconList.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }

  try {
    const data = await apiFetch("/admin/sports/overview");
    sportsList.innerHTML = `<div class="admin-btn-row" style="margin-bottom:12px"><button id="admin-sports-create">➕ ግጥሚያ ጨምር</button></div>`;
    document.getElementById("admin-sports-create").onclick = () => {
      if (document.getElementById("sports-form-back")) return;
      const pad = (n) => String(n).padStart(2, "0");
      const d0 = new Date(Date.now() + 2 * 3600 * 1000);           // default kickoff: 2 hours from now
      const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      const back = document.createElement("div"); back.id = "sports-form-back"; back.className = "kh-back";
      back.innerHTML = `<div class="kh-card sp-form" role="dialog" aria-modal="true">
        <h3>⚽ አዲስ ግጥሚያ</h3>
        <div class="sp-preview"><span id="spf-ch">${teamCrest("Home", 52)}</span><b>VS</b><span id="spf-ca">${teamCrest("Away", 52)}</span></div>
        <div class="sp-odds"><div><label>Sport</label><select id="spf-sport"><option value="football">⚽ Football</option><option value="basketball">🏀 Basketball</option><option value="tennis">🎾 Tennis</option></select></div><div><label>League</label><input id="spf-league" type="text" maxlength="40" autocomplete="off" placeholder="Premier League"></div></div>
        <label>Home team</label><input id="spf-home" type="text" maxlength="60" autocomplete="off">
        <label>Away team</label><input id="spf-away" type="text" maxlength="60" autocomplete="off">
        <div class="sp-odds"><div><label>🛡 Home አርማ (ፎቶ)</label><input id="spf-hlogo" type="file" accept="image/jpeg,image/png,image/webp"></div><div><label>🛡 Away አርማ (ፎቶ)</label><input id="spf-alogo" type="file" accept="image/jpeg,image/png,image/webp"></div></div>
        <div class="sp-odds">
          <div><label>Home</label><input id="spf-oh" type="number" inputmode="decimal" step="0.01" min="1.01" value="2.00"></div>
          <div><label>Draw</label><input id="spf-od" type="number" inputmode="decimal" step="0.01" min="1.01" value="3.20"></div>
          <div><label>Away</label><input id="spf-oa" type="number" inputmode="decimal" step="0.01" min="1.01" value="3.00"></div>
        </div>
        <small id="spf-margin"></small>
        <label>Kickoff / betting ይዘጋል (የኢትዮጵያ ሰዓት)</label>
        <input id="spf-closes" type="datetime-local" value="${fmt(d0)}" min="${fmt(new Date())}">
        <small id="spf-status" class="mkt-edit-status"></small>
        <div class="admin-btn-row"><button type="button" id="spf-save">✅ ጨምር</button><button type="button" id="spf-cancel">ሰርዝ</button></div>
      </div>`;
      document.body.appendChild(back);
      const $ = (id) => document.getElementById(id), close = () => back.remove();
      const margin = () => {
        const oh = parseFloat($("spf-oh").value), od = parseFloat($("spf-od").value), oa = parseFloat($("spf-oa").value), el = $("spf-margin");
        if (!(oh > 1 && od > 1 && oa > 1)) { el.textContent = ""; return; }
        const two = $("spf-sport") && $("spf-sport").value !== "football"; const m = 1 / oh + (two ? 0 : 1 / od) + 1 / oa;
        el.textContent = `House margin: ${((m - 1) * 100).toFixed(1)}% ${m < 1.02 ? "⚠️ በጣም ትንሽ -- odds ዝቀሱ (ቢያንስ ~2%)" : "✅"}`;
      };
      ["spf-oh", "spf-od", "spf-oa"].forEach((id) => $(id).addEventListener("input", margin)); margin();
      $("spf-sport").addEventListener("change", () => { $("spf-od").parentElement.style.display = $("spf-sport").value === "football" ? "" : "none"; margin(); });
      $("spf-home").addEventListener("input", () => { if (!$("spf-hlogo").files[0]) $("spf-ch").innerHTML = teamCrest($("spf-home").value || "Home", 52); });
      $("spf-away").addEventListener("input", () => { if (!$("spf-alogo").files[0]) $("spf-ca").innerHTML = teamCrest($("spf-away").value || "Away", 52); });
      const pickLogo = (inputId, boxId, fallbackId) => $(inputId).addEventListener("change", () => {
        const f = $(inputId).files[0];
        if (f && f.size > 2 * 1024 * 1024) { $("spf-status").textContent = "❌ አርማው ከ2MB መብለጥ የለበትም"; $(inputId).value = ""; return; }
        if (f) $(boxId).innerHTML = `<img class="team-crest" src="${URL.createObjectURL(f)}" width="52" height="52" style="object-fit:contain;border-radius:8px" alt="">`;
        else $(boxId).innerHTML = teamCrest($(fallbackId).value || "Team", 52);
      });
      pickLogo("spf-hlogo", "spf-ch", "spf-home"); pickLogo("spf-alogo", "spf-ca", "spf-away");
      $("spf-cancel").onclick = close; back.addEventListener("click", (e) => { if (e.target === back) close(); });
      $("spf-save").onclick = async () => {
        const st = $("spf-status"), home = $("spf-home").value.trim(), away = $("spf-away").value.trim(), closes_at = $("spf-closes").value;
        if (!home || !away) { st.textContent = "❌ የሁለቱንም ቡድን ስም ያስገቡ"; return; }
        if (!closes_at) { st.textContent = "❌ Kickoff ቀንና ሰዓት ይምረጡ"; return; }
        $("spf-save").disabled = true;
        try {
          const fd = new FormData();
          fd.append("home_team", home); fd.append("away_team", away);
          fd.append("odds_home", $("spf-oh").value); fd.append("odds_away", $("spf-oa").value);
          if ($("spf-sport").value === "football") fd.append("odds_draw", $("spf-od").value);
          fd.append("closes_at", closes_at); fd.append("sport", $("spf-sport").value); fd.append("league", $("spf-league").value.trim());
          if ($("spf-hlogo").files[0]) fd.append("home_logo", $("spf-hlogo").files[0]);
          if ($("spf-alogo").files[0]) fd.append("away_logo", $("spf-alogo").files[0]);
          await apiFetch("/admin/sports/match", { method: "POST", formData: fd });
          close(); haptic("success"); loadAdminLogs();
        } catch (e) { st.textContent = "❌ " + e.message; $("spf-save").disabled = false; haptic("error"); }
      };
    };
    if (!data.matches.length) {
      sportsList.insertAdjacentHTML("beforeend", `<div class="empty-state">ምንም ግጥሚያ የለም</div>`);
    }
    for (const m of data.matches) {
      const div = document.createElement("div");
      div.className = "admin-list-card";
      const started = m.closes_at && String(m.closes_at) <= new Date(Date.now()).toLocaleString("sv-SE").slice(0, 19);
      div.innerHTML = `
        <div class="adm-match-head">${teamCrest(m.home_team, 30, m.home_logo)}<b>${escapeHtml(m.home_team)}</b> <span>vs</span> <b>${escapeHtml(m.away_team)}</b>${teamCrest(m.away_team, 30, m.away_logo)}</div>
        <small>#${m.id} · ${escapeHtml(m.status)}${m.status === "OPEN" ? (started ? " · 🔴 LIVE" : " · ⏳ " + escapeHtml(String(m.closes_at || "").slice(0, 16))) : ""} · Bets: ${m.bet_count} · Staked: ${m.total_staked.toFixed(2)} ብር</small>
        ${m.status === "OPEN" ? `
          <div class="adm-live-row"><input class="lv-h" type="number" min="0" max="99" inputmode="numeric" value="${m.home_score ?? 0}"><b>-</b><input class="lv-a" type="number" min="0" max="99" inputmode="numeric" value="${m.away_score ?? 0}"><input class="lv-m" type="text" maxlength="8" placeholder="ደቂቃ 67'" value="${escapeHtml(m.live_minute || "")}"><button class="lv-save">📺 Live አዘምን</button></div>
          <div class="admin-btn-row"><button class="sp-close">⏹ Betting ዝጋ</button></div>
          <div class="adm-settle-row"><span>⚖️ ውጤት:</span><button data-r="HOME">1 Home</button><button data-r="DRAW">X Draw</button><button data-r="AWAY">2 Away</button><button data-r="VOID">Void</button></div>
          <small class="sp-msg"></small>`
        : `<small>Result: ${escapeHtml(m.result || "-")}${m.home_score != null ? ` · ${m.home_score}-${m.away_score}` : ""}</small>`}
      `;
      sportsList.appendChild(div);
      if (m.status !== "OPEN") continue;
      const msg = div.querySelector(".sp-msg");
      div.querySelector(".lv-save").onclick = async () => {
        try { await apiFetch("/admin/sports/live", { method: "POST", json: { match_id: m.id, home_score: parseInt(div.querySelector(".lv-h").value || "0", 10), away_score: parseInt(div.querySelector(".lv-a").value || "0", 10), minute: div.querySelector(".lv-m").value } }); msg.textContent = "✅ Live score ተዘምኗል"; haptic("success"); }
        catch (e) { msg.textContent = "❌ " + e.message; haptic("error"); }
      };
      div.querySelector(".sp-close").onclick = async () => {
        if (!confirm("Betting ይዘጋ? (ከዚያ በኋላ ማንም መወራረድ አይችልም)")) return;
        try { await apiFetch("/admin/sports/close", { method: "POST", json: { match_id: m.id } }); msg.textContent = "✅ Betting ተዘግቷል"; haptic("success"); } catch (e) { msg.textContent = "❌ " + e.message; }
      };
      div.querySelectorAll(".adm-settle-row button").forEach((b) => b.onclick = async () => {
        const r = b.dataset.r;
        if (!confirm(`${m.home_team} vs ${m.away_team}: ውጤት "${r}" ይሁን? ክፍያ ወዲያው ይከፈላል -- መመለስ አይቻልም።`)) return;
        try { await apiFetch("/admin/sports/settle", { method: "POST", json: { match_id: m.id, result: r } }); haptic("success"); loadAdminLogs(); }
        catch (e) { msg.textContent = "❌ " + e.message; haptic("error"); }
      });
    }
  } catch (e) {
    sportsList.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }

  try {
    const data = await apiFetch("/admin/actions/recent?limit=30");
    actionsList.innerHTML = "";
    if (!data.actions.length) {
      actionsList.innerHTML = `<div class="empty-state">ገና ምንም action የለም</div>`;
    }
    for (const a of data.actions) {
      const div = document.createElement("div");
      div.className = "admin-log-line";
      div.textContent = `[${a.created_at}] admin#${a.admin_id} -- ${a.action_type}: ${JSON.stringify(a.details)}`;
      actionsList.appendChild(div);
    }
  } catch (e) {
    actionsList.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }

  try {
    const data = await apiFetch("/admin/errors/recent?limit=30");
    errorsList.innerHTML = "";
    if (!data.lines.length) {
      errorsList.innerHTML = `<div class="empty-state">🎉 ምንም የቅርብ ጊዜ error የለም</div>`;
    }
    for (const line of data.lines) {
      const div = document.createElement("div");
      div.className = "admin-log-line admin-error-line";
      div.textContent = line;
      errorsList.appendChild(div);
    }
  } catch (e) {
    errorsList.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}


async function submitSupportTicket() {
  const input=document.getElementById("support-message-input"); const file=document.getElementById("support-photo-input"); const status=document.getElementById("support-status");
  if(!input || (!input.value.trim() && !(file?.files?.length))) { if(status) status.textContent="መልዕክት ወይም Photo ያስገቡ"; return; }
  try {
    const fd=new FormData(); fd.append("subject","Mini App Support"); fd.append("message",input.value.trim());
    if(file?.files?.length) fd.append("photo",file.files[0]);
    const r=await apiFetch("/support/tickets",{method:"POST",formData:fd}); input.value=""; if(file) file.value=""; if(status) status.textContent=`✅ Ticket #${r.ticket_id} ተልኳል`;
  } catch(e){ if(status) status.textContent="❌ "+e.message; }
}

async function loadAdminSupportTickets(){
  const box=document.getElementById("admin-support-list"); if(!box) return;
  try {
    const r=await apiFetch("/admin/support/tickets");
    const items=r.items||[];
    box.innerHTML=items.map(x=>`<div class="admin-log-line" data-t="${x.ticket_id}"><b>#${x.ticket_id}</b> User ${x.user_id} — ${escapeHtml(x.status)} — ${escapeHtml(x.updated_at)}<div class="admin-note">${escapeHtml((x.last_sender==="admin"?"↩ ":"")+(x.last_message||x.subject||""))}</div><button class="admin-mini-read" data-ticket="${x.ticket_id}">Read</button> ${x.status==="closed"?"":`<button class="admin-mini-support" data-ticket="${x.ticket_id}">Reply</button> <button class="admin-mini-close" data-ticket="${x.ticket_id}">Close</button>`}<div class="admin-ticket-thread"></div></div>`).join("")||"ምንም ticket የለም";
    box.querySelectorAll(".admin-mini-read").forEach(b=>b.addEventListener("click",async()=>{
      const th=b.closest(".admin-log-line").querySelector(".admin-ticket-thread");
      if(th.innerHTML){ th.innerHTML=""; return; }
      try{ const d=await apiFetch(`/admin/support/tickets/${b.dataset.ticket}`);
        th.innerHTML=(d.messages||[]).map(m=>`<div class="admin-note"><b>${m.sender_role==="admin"?"Admin":"User"}</b> · ${escapeHtml(m.created_at)}<br>${escapeHtml(m.message_text||("["+(m.media_type||"media")+"]"))}</div>`).join("")||"—";
      }catch(e){ th.textContent="❌ "+e.message; }
    }));
    box.querySelectorAll(".admin-mini-support").forEach(b=>b.addEventListener("click",async()=>{const msg=prompt("Reply message:"); if(!msg) return; try{await apiFetch(`/admin/support/tickets/${b.dataset.ticket}/reply`,{method:"POST",json:{message:msg}}); loadAdminSupportTickets();}catch(e){alert(e.message)}}));
    box.querySelectorAll(".admin-mini-close").forEach(b=>b.addEventListener("click",async()=>{if(!confirm("Ticket #"+b.dataset.ticket+" ይዘጋ?")) return; try{await apiFetch(`/admin/support/tickets/${b.dataset.ticket}/close`,{method:"POST",json:{}}); loadAdminSupportTickets();}catch(e){alert(e.message)}}));
  } catch(e){box.textContent="❌ "+e.message;}
}

async function sendAdminAnnouncement(){
  const msg=document.getElementById("admin-announcement-text")?.value.trim();
  const media=document.getElementById("admin-announcement-media")?.files?.[0];
  const status=document.getElementById("admin-announcement-status");
  const game=document.getElementById("admin-announcement-game")?.value||"lobby";
  if(!msg){if(status) status.textContent="የማስታወቂያ መልዕክት ያስገቡ";return;}
  if(media && media.size>8*1024*1024){if(status)status.textContent="❌ ፋይሉ ከ8MB መብለጥ የለበትም";return;}
  try{
    let r;
    if(media){const fd=new FormData();fd.append("message",msg);fd.append("game",game);fd.append("media",media);r=await apiFetch("/admin/announcements/broadcast",{method:"POST",formData:fd});}
    else {r=await apiFetch("/admin/announcements/broadcast",{method:"POST",json:{message:msg,game}});}
    if(status)status.textContent=`✅ ተልኳል: ${r.sent}/${r.total_targets} · አልተሳካም: ${r.failed}${r.channel_posted?" · Channel ላይ ተለጥፏል":""}`;
  }catch(e){if(status)status.textContent="❌ "+e.message;}
}

async function loadSupportContact() {
  try {
    const data = await apiFetch("/support-info");
    const text = `📞 ${data.support_contact || data.contact || "Support"}`;
    ["support-contact-line", "support-contact-line-2", "support-contact-line-3"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    });
  } catch (e) {
    // Non-critical -- the rest of the app works fine without this.
  }
}

async function main() {

  tg.ready();
  tg.expand();
  applyTelegramTheme();

  // Reconcile server-backed state whenever Telegram/Android returns the
  // Mini App from background; never rely on a stale in-memory wallet/listing.
  const refreshOnResume = () => {
    if (document.visibilityState && document.visibilityState !== "visible") return;
    refreshBalance();
    const marketPage = document.getElementById("page-marketplace");
    if (marketPage && marketPage.classList.contains("active")) loadMarketplace();
  };
  document.addEventListener("visibilitychange", refreshOnResume);
  window.addEventListener("pageshow", refreshOnResume);

  setupNav();
  setupCategoryChips();
  setupWalletSubtabs();
  setupDepositForm();
  setupWithdrawForm();
  setupInvite();
  setupLegalLinks();
  setupBoomHistory();
  setupNumberHistory();
  setupAdminPanel();
  setupSelfExclusion();
  setupMarketplaceTabs();
  document.getElementById("support-send-btn")?.addEventListener("click", submitSupportTicket);
  document.getElementById("admin-announcement-send")?.addEventListener("click", sendAdminAnnouncement);
  ensureAddedGamePages();
  renderGameGrid();
  renderNumberGrid();
  loadSupportContact();

  document.getElementById("open-bot-chat").addEventListener("click", () => tg.close());
  document.getElementById("history-more").addEventListener("click", () => loadHistory(false));
  document.getElementById("boom-leave").addEventListener("click", leaveBoom);

  try {
    // Reopening the Mini App while the (free) server is asleep makes the first call fail or hang for a while.
    // Retry a few times with a visible message instead of showing an error / half-empty screen.
    const loadingEl = document.getElementById("loading");
    let lastErr = null;
    for (let attempt = 1; attempt <= 6; attempt++) {
      try { await loadProfile(); lastErr = null; break; }
      catch (err) {
        lastErr = err;
        const msg = String(err && err.message || "");
        if (/Session expired|terms_not_accepted|banned|self_excluded/i.test(msg) || attempt === 6) break;
        if (loadingEl) loadingEl.textContent = "⏳ ሰርቨሩ እየነቃ ነው... (" + attempt + "/5)";
        await new Promise((r) => setTimeout(r, 1500 * attempt));
      }
    }
    if (lastErr) throw lastErr;
    loadWinsTicker();
    setInterval(loadWinsTicker, 30000); // refresh ticker every 30s
    document.getElementById("loading").style.display = "none";
    document.getElementById("content").style.display = "block";
    try { window.scrollTo(0, 0); } catch (_) {}
    openDeepLink();
  } catch (e) {
    showError(e.message);
  }
}

// Posts published by the admin (channel / bot) open the Mini App directly on the chosen game:
//   t.me/<bot>?startapp=g_keno  -> Telegram start_param "g_keno"      |   web_app button url  ...?game=keno
function openDeepLink() {
  let key = "";
  try {
    const sp = tg.initDataUnsafe && tg.initDataUnsafe.start_param;
    // Invite link opened straight in the Mini App: t.me/<bot>/<app>?startapp=ref_<id>  -> count the invite once.
    if (sp && /^ref_\d{1,15}$/.test(sp)) {   // server counts it only once, for a brand-new account
      apiFetch("/referral/claim", { method: "POST", json: { code: sp } }).catch(() => {});
    }
    if (sp && /^g_[A-Za-z0-9_-]{1,40}$/.test(sp)) key = sp.slice(2);
  } catch (_) { /* ignore */ }
  if (!key) { try { key = new URLSearchParams(location.search).get("game") || ""; } catch (_) { /* ignore */ } }
  key = String(key).toLowerCase();
  if (!/^[a-z0-9_]{1,40}$/.test(key) || key === "lobby" || key === "home") return;
  setTimeout(() => {
    try { goToPage(key); haptic("light"); }
    catch (_) { try { goToPage("lobby"); } catch (__) { /* ignore */ } }   // unknown key -> never leave a blank screen
  }, 80);
}

runAgeGate(main);

/* ============================================================
   V3 SERVER-STATEFUL ROUND CLIENT
============================================================ */
const realtimeRounds = new Map();
const pendingRoundStarts = new Map();
function makeClientSeed(){return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2,'0')).join('');}
async function startRealtimeRound(key, body){
  const fingerprint=JSON.stringify(body);
  let pending=pendingRoundStarts.get(key);
  if(!pending||pending.fingerprint!==fingerprint){pending={fingerprint,client_seed:makeClientSeed()};pendingRoundStarts.set(key,pending);}
  const requestBody={...body,client_seed:pending.client_seed};
  try{
    const r=await apiFetch(`/games/${key}/round/start`,{method:'POST',json:requestBody});
    realtimeRounds.set(key,r); return r;
  }catch(e){
    if(e.body&&e.body.round_id&&e.body.status==='ACTIVE'){realtimeRounds.set(key,e.body);return e.body;}
    throw e;
  }
}
async function realtimeState(key){
  const r=realtimeRounds.get(key); if(!r) return null;
  return apiFetch(`/games/${key}/round/${r.round_id}/state`);
}
async function realtimeAction(key,action){
  const r=realtimeRounds.get(key); if(!r) throw new Error('No active server round');
  try{
    const result=await apiFetch(`/games/${key}/round/${r.round_id}/action`,{method:'POST',json:{action}});
    if(result&&['WON','LOST','REFUNDED'].includes(result.status))pendingRoundStarts.delete(key);
    return result;
  }catch(e){
    let b=e.body;
    if(!(b&&['WON','LOST','REFUNDED'].includes(b.status))){try{const st=await realtimeState(key);if(st&&['WON','LOST','REFUNDED'].includes(st.status))b=st;}catch(_){}}
    if(b&&['WON','LOST','REFUNDED'].includes(b.status)){pendingRoundStarts.delete(key);return {...b,ok:true,won:b.status==='WON',refunded:b.status==='REFUNDED',payout:Number(b.payout??b.outcome?.payout??0),outcome:b.outcome||{},round_code:b.round_code||r.round_code};}
    throw e;
  }
}


// Win/loss line shown to the player. Everything is NET of the stake: a payout
// below the stake is a (partial) loss and is never announced as a win.
function resultLine(rr,stake,loseText,winWord){
  const payout=Number(rr.payout||0), st=Number(stake||0), net=Math.round((payout-st)*100)/100;
  if(rr.refunded) return `↩️ Round timeout — ${payout.toFixed(2)} ብር ተመላሽ ሆኗል`;
  if(net>0) return `🎉 <b>${winWord}</b> +${net.toFixed(2)} ብር <small>(ክፍያ ${payout.toFixed(2)} ብር)</small>`;
  if(payout>0&&net<0) return `↩️ ከፊል ክፍያ ${payout.toFixed(2)} ብር — የተጣራ ${net.toFixed(2)} ብር`;
  if(payout>0) return `↔️ Stake ተመልሷል (${payout.toFixed(2)} ብር)`;
  return loseText;
}

async function playAddedGame(key){
  const controls=document.getElementById(key+'-controls'), result=document.getElementById(key+'-result'), btn=document.getElementById(key+'-play');
  let body={}; const stakeEl=document.getElementById(key+'-stake'); const stake=stakeEl?Number(stakeEl.value):10;
  if(!(stake>0)) return renderActionError(result,'የBet መጠን ትክክል ያስገቡ');
  if(key==='dice'){const guess=Number(document.getElementById('dice-value').value);if(!guess)return renderActionError(result,'እባክዎ ዳይስ ቁጥር ይምረጡ');body={stake,guess};}
  if(key==='slot'||key==='wheel'||key==='plinko')body={stake};
  if(key==='plinko'&&window.__plinko)body={stake,risk:window.__plinko.risk,rows:window.__plinko.rows};
  if(key==='keno'){const numbers=[...controls.querySelectorAll('.choice-btn.selected')].map(b=>Number(b.dataset.value));if(numbers.length<1||numbers.length>10)return renderActionError(result,'ከ1 እስከ 10 ቁጥሮች ይምረጡ');body={stake,numbers,grid:80};}
  if(key==='aviator')body={stake}; if(key==='jet')body={stake};
  if(key==='aviator'||key==='jet'){const ac=parseFloat(document.getElementById(key+'-cashout')?.value);if(ac>=1.01)body.auto_cashout=Math.round(ac*100)/100;}
  if(key==='mines')body={stake,mines:Number(document.getElementById('mines-count').value),pick:Number(document.getElementById('mines-pick').value)};
  if(key==='fish')body={stake,shot:Number(document.getElementById('fish-shot').value)};
  if(key==='card')body={stake,choice:controls.querySelector('.choice-btn.selected')?.dataset.value||''};
  if(key==='coinflip'||key==='penalty'){const ch=controls.querySelector('.choice-btn.selected')?.dataset.value||'';if(!ch)return renderActionError(result,key==='coinflip'?'Heads ወይም Tails ይምረጡ':'የመምቻ ጎን ይምረጡ');body={stake,choice:ch};}
  btn.disabled=true; result.textContent='⏳ Server round እየጀመረ...';
  try{
    const r=await startRealtimeRound(key,body); render3DScene(key,{},'playing'); renderThreeGameScene(key,{},'playing');
    if(key==='aviator'||key==='jet'){
      result.innerHTML=`<div class="round-proof"><b>ROUND ${escapeHtml(r.round_code)}</b> · LIVE SERVER ROUND · COMMIT ${escapeHtml((r.seed_commit||r.commitment||'').slice(0,16))}… · CLIENT SEED ${escapeHtml((r.client_seed||'').slice(0,16))}…</div>`;
      const cashBtn=document.createElement('button');cashBtn.className='primary-game-btn';cashBtn.textContent='💸 CASH OUT';cashBtn.type='button';btn.insertAdjacentElement('afterend',cashBtn);
      let stopped=false, resolveRound;
      const roundDone=new Promise(resolve=>{resolveRound=resolve;});
      const tick=async()=>{if(stopped)return;try{const st=await realtimeState(key);const mult=Number(st.live_multiplier||1);const el=document.getElementById(key+'-live-mult');if(el)el.textContent=mult.toFixed(2)+'×';render3DScene(key,{live_multiplier:mult},'playing');renderThreeGameScene(key,{live_multiplier:mult},'playing');if(st.phase==='CRASHED'||st.status==='WON'){stopped=true;cashBtn.disabled=true;try{resolveRound(await realtimeAction(key,'cashout'));}catch(_){resolveRound(null);}return;}setTimeout(tick,300);}catch(_){setTimeout(tick,600);}};tick();
      cashBtn.onclick=async()=>{if(stopped)return;cashBtn.disabled=true;stopped=true;try{resolveRound(await realtimeAction(key,'cashout'));}catch(e){renderActionError(result,e.message);resolveRound(null);}};
      const rr=await roundDone; stopped=true; cashBtn.remove();
      if(rr){const eff=Number(rr.payout||0)/Math.max(0.01,Number(body.stake||1));const rtp=Number(rr.rtp||rr.outcome?.rtp||0)*100;result.innerHTML=`<div class="round-proof"><b>ROUND ${escapeHtml(rr.round_code||r.round_code)}</b> · SERVER SEED REVEALED · CLIENT SEED ${escapeHtml((r.client_seed||'').slice(0,16))}…</div>`+resultLine(rr,body.stake,`❌ CRASH — 0 ብር`,'WIN')+`<div class="payout-disclosure">Effective payout: <b>${eff.toFixed(2)}×</b> · Configured RTP: <b>${rtp.toFixed(1)}%</b></div>`;renderThreeGameScene(key,rr,rr.won?'win':'lose');rr.won?(gameSound('win'),haptic('success')):(gameSound('lose'),haptic('error'));loadProfile();}
    }else{
      for(let i=0;i<3;i++){const st=await realtimeState(key);result.innerHTML=`<div class="round-live-badge">🟢 ROUND ${escapeHtml(r.round_code)} · LIVE</div><div class="round-progress"><i style="width:${Math.max(20,(i+1)*33)}%"></i></div>`;render3DScene(key,{progress:(i+1)/3},'playing');renderThreeGameScene(key,{progress:(i+1)/3},'playing');await new Promise(res=>setTimeout(res,140));}
      const rr=await realtimeAction(key,'play'); const eff=Number(rr.payout||0)/Math.max(0.01,Number(body.stake||1)); const rtp=Number(rr.outcome?.rtp||0)*100; result.innerHTML=`<div class="round-proof"><b>ROUND ${escapeHtml(rr.round_code||r.round_code)}</b> · SERVER SEED REVEALED · CLIENT SEED ${escapeHtml((r.client_seed||'').slice(0,16))}…</div>`+resultLine(rr,body.stake,`❌ አልተሳካም`,'አሸንፈዋል!')+`<div class="payout-disclosure">Effective payout: <b>${eff.toFixed(2)}×</b> · Configured RTP: <b>${rtp.toFixed(1)}%</b></div>`;animateGameResult(key,result,!!rr.won&&Number(rr.payout||0)>Number(body.stake||0),rr.outcome||{});(rr.won&&Number(rr.payout||0)>Number(body.stake||0))?(gameSound('win'),haptic('success')):(gameSound('lose'),haptic('error'));loadProfile();
    }
  }catch(e){renderActionError(result,e.message);}finally{btn.disabled=false;}
}

// Replace the legacy play listener after the UI builder creates controls.
const _legacySetupAddedGameControls = setupAddedGameControlsLegacy;
setupAddedGameControls = function(key){
  if(key==='chicken'&&typeof window.setupChickenRoad==='function'){window.setupChickenRoad();return;}
  if(key==='rabbit'&&typeof window.setupRabbitRoad==='function'){window.setupRabbitRoad();return;}
  { const hook={dice2:'setupDice2',coinstreak:'setupCoinStreak',roast:'setupRoast',wheel:'setupWheel',slot:'setupSlot',penaltystreak:'setupPenaltyStreak',tower:'setupTower',chicken2:'setupChicken2',roulette:'setupRoulette',bingo:'setupBingo',fastkeno:'setupFastKeno',baccarat:'setupBaccarat',dragontiger:'setupDragonTiger',andarbahar:'setupAndarBahar',blackjack:'setupBlackjack',aviator:'setupAviator',mines:'setupMines',triplegold:'setupTripleGold',flame:'setupFlame',aztec:'setupAztec',buffalo:'setupBuffalo',plinko:'setupPlinko',keno:'setupKeno',fish:'setupFish'}[key]; if(hook&&typeof window[hook]==='function'){window[hook]();return;} } // interactive Chicken Road (road_game.js)
  _legacySetupAddedGameControls(key);
  const oldBtn=document.getElementById(key+'-play'); if(!oldBtn||oldBtn.dataset.v3Bound)return;
  const btn=oldBtn.cloneNode(true);oldBtn.replaceWith(btn);btn.dataset.v3Bound='1';btn.addEventListener('click',()=>playAddedGame(key));
};
