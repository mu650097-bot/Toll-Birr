/* KDM IN-GAME SCREENS (phase 1: look only). Wraps existing game pages in the new header + bet stepper + chips.
   It only moves/restyles existing elements and writes the bet into the SAME input the game already reads. */
(function () {
  "use strict";
  var CHIPS = [10, 50, 100, 500];
  function fire(inp) { inp.dispatchEvent(new Event("input", { bubbles: true })); inp.dispatchEvent(new Event("change", { bubbles: true })); }
  function setVal(inp, v) {
    var min = parseFloat(inp.min) || 0.01, max = parseFloat(inp.max) || Infinity;
    v = Math.max(min, Math.min(v, max));
    inp.value = (Math.round(v * 100) / 100).toString();
    fire(inp);
  }
  function stepFor(v) { return v >= 1000 ? 100 : v >= 100 ? 10 : v >= 20 ? 5 : 1; }

  function header(page) {
    if (page.dataset.kdmIgHead) return;
    var back = page.querySelector(":scope > .back-btn, :scope > .page-head .back-btn") || page.querySelector(".back-btn");
    var title = page.querySelector(":scope > h2, :scope > h3, :scope > .page-head h2, :scope > .page-head h3") || page.querySelector("h2");
    if (!back || !title || back.parentNode !== title.parentNode) return;
    page.dataset.kdmIgHead = "1";
    var head = document.createElement("div"); head.className = "kdm-ig-head";
    back.parentNode.insertBefore(head, back);
    head.appendChild(back); head.appendChild(title);
    var live = document.createElement("div"); live.className = "kdm-ig-live"; live.textContent = "Live";
    head.appendChild(live);
  }

  // other scripts (help button, tags) insert right after the <h2>, which is inside our header now -> move them below it
  function tidyQuick() {
    document.querySelectorAll(".kdm-ig-stepper > .kdm-stake-quick, .kx-step > .kdm-stake-quick").forEach(function (q) {
      var host = q.parentNode, chips = host.nextElementSibling;
      var after = (chips && chips.classList.contains("kdm-ig-chips")) ? chips : host;
      after.insertAdjacentElement("afterend", q);
    });
  }
  function tidyHeads() {
    document.querySelectorAll(".kdm-ig-head").forEach(function (head) {
      Array.prototype.slice.call(head.children).forEach(function (c) {
        if (c.classList.contains("back-btn") || c.classList.contains("kdm-ig-live") || c.tagName === "H2" || c.tagName === "H3") return;
        head.parentNode.insertBefore(c, head.nextSibling);
      });
    });
  }

  function stepper(inp) {
    if (inp.dataset.kdmIg) return;
    inp.dataset.kdmIg = "1";
    if (inp.closest(".kx-step")) return;
    var wrap = document.createElement("div"); wrap.className = "kdm-ig-stepper";
    var minus = document.createElement("button"); minus.type = "button"; minus.setAttribute("aria-label", "Decrease bet"); minus.textContent = "\u2212";
    var plus = document.createElement("button"); plus.type = "button"; plus.setAttribute("aria-label", "Increase bet"); plus.textContent = "+";
    inp.parentNode.insertBefore(wrap, inp);
    wrap.appendChild(minus); wrap.appendChild(inp); wrap.appendChild(plus);
    minus.addEventListener("click", function () { var v = parseFloat(inp.value) || 0; setVal(inp, v - stepFor(v)); });
    plus.addEventListener("click", function () { var v = parseFloat(inp.value) || 0; setVal(inp, v + stepFor(v)); });
    // road / table / roulette-style pages already ship their own chip row -> keep only the stepper there
    if (inp.closest(".cr-page, .ng-page, .cu-page")) return;
    var chips = document.createElement("div"); chips.className = "kdm-ig-chips";
    CHIPS.forEach(function (c) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = String(c); b.dataset.v = String(c);
      b.addEventListener("click", function () { setVal(inp, c); });
      chips.appendChild(b);
    });
    wrap.insertAdjacentElement("afterend", chips);
    function mark() { var v = parseFloat(inp.value); chips.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", parseFloat(b.dataset.v) === v); }); }
    inp.addEventListener("input", mark); inp.addEventListener("change", mark); mark();
  }

  function run() {
    document.querySelectorAll(".page").forEach(function (p) { if (p.querySelector("input.game-stake") || p.id === "page-boom" || p.id === "page-number") header(p); });
    document.querySelectorAll("input.game-stake").forEach(stepper);
    tidyHeads();
    tidyQuick();
    document.body.classList.toggle("kdm-ig-on", !!document.querySelector(".page.active .kdm-ig-head"));
  }
  var q = false;
  function onMutate() { if (q) return; q = true; requestAnimationFrame(function () { q = false; run(); }); }
  function boot() { run(); if (window.MutationObserver) new MutationObserver(onMutate).observe(document.body, { childList: true, subtree: true });
    var pg = document.getElementById("pages");
    if (pg && window.MutationObserver) new MutationObserver(onMutate).observe(pg, { attributes: true, attributeFilter: ["class"], subtree: true }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
