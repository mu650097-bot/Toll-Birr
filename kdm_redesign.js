/* ==========================================================================
   KDM Mini App - UI redesign helpers (presentation only)
   Loaded last. It never touches game logic, balances or API calls.
   1. Mirrors the header balance into the Wallet balance card.
   2. Adds data-state="success|error|loading" to status messages so the CSS
      can show them as clear success / error / loading banners.
   ========================================================================== */
(function () {
  "use strict";

  // 1. Wallet balance card mirrors #balance (which app.js animates).
  function mirrorBalance() {
    const src = document.getElementById("balance");
    if (!src) return;
    const sync = () => {
      document.querySelectorAll("[data-mirror-balance]").forEach((el) => { el.textContent = src.textContent; });
    };
    sync();
    new MutationObserver(sync).observe(src, { childList: true, characterData: true, subtree: true });
  }

  // 2. Status banners. app.js writes plain text such as "✅ ...", "❌ ...", "⏳ ...".
  const STATUS_SELECTOR = [
    '[id$="-status"]', ".market-status", ".bet-status", ".mkt-edit-status", ".mkt-review-status",
    ".mkt-deliver-status", ".admin-game-status",
  ].join(",");

  function stateOf(text) {
    const t = (text || "").trim();
    if (!t) return "";
    if (/^(✅|✔|🟢)/.test(t)) return "success";
    if (/^(❌|⚠|🔴|🚫)/.test(t)) return "error";
    if (/^(⏳|🔄|📡)/.test(t)) return "loading";
    return "info";
  }

  function paint(el) {
    if (!el || !el.matches || !el.matches(STATUS_SELECTOR)) return;
    // The wins ticker / admin panels have their own look: leave them alone.
    if (el.closest("#page-admin")) return;
    const s = stateOf(el.textContent);
    if (el.getAttribute("data-state") !== s) el.setAttribute("data-state", s);
  }

  function paintFrom(node) {
    let el = node.nodeType === 3 ? node.parentElement : node;
    while (el && el !== document.body) {
      if (el.matches && el.matches(STATUS_SELECTOR)) { paint(el); return; }
      el = el.parentElement;
    }
  }

  function watchStatuses() {
    const root = document.getElementById("pages");
    if (!root) return;
    root.querySelectorAll(STATUS_SELECTOR).forEach(paint);
    new MutationObserver((muts) => {
      for (const m of muts) {
        paintFrom(m.target);
        m.addedNodes && m.addedNodes.forEach((n) => {
          if (n.nodeType === 1) {
            if (n.matches && n.matches(STATUS_SELECTOR)) paint(n);
            n.querySelectorAll && n.querySelectorAll(STATUS_SELECTOR).forEach(paint);
          }
        });
      }
    }).observe(root, { childList: true, characterData: true, subtree: true });
  }

  function init() {
    mirrorBalance();
    watchStatuses();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
