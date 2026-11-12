/* KDM FIX LAYER (loaded last): if Telegram/Android leaves the page scrolled sideways (after reopening the Mini App,
   rotating, or the keyboard), put it back so the screen is never half-empty. */
(function () {
  "use strict";
  function resetX() {
    try {
      if (window.scrollX || document.documentElement.scrollLeft || document.body.scrollLeft) {
        window.scrollTo(0, window.scrollY || 0);
        document.documentElement.scrollLeft = 0; document.body.scrollLeft = 0;
      }
    } catch (e) { /* ignore */ }
  }
  window.addEventListener("scroll", resetX, { passive: true });
  window.addEventListener("resize", resetX);
  window.addEventListener("orientationchange", resetX);
  window.addEventListener("pageshow", resetX);
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") { resetX(); setTimeout(resetX, 250); } });
  try {
    var tg = window.Telegram && window.Telegram.WebApp;
    if (tg && tg.onEvent) { tg.onEvent("viewportChanged", resetX); tg.onEvent("activated", resetX); }
  } catch (e) { /* ignore */ }
  setTimeout(resetX, 300); setTimeout(resetX, 1500);
})();
