/* PREMIUM UI/MOTION LAYER - visual only. Never touches API/money logic. */
(function(){
  "use strict";
  var reduce=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;
  // 1) button ripple
  document.addEventListener("pointerdown",function(e){
    var b=e.target.closest&&e.target.closest("button");
    if(!b||b.disabled||reduce)return;
    var r=b.getBoundingClientRect(),s=Math.max(r.width,r.height),el=document.createElement("span");
    el.className="ripple";
    el.style.cssText="width:"+s+"px;height:"+s+"px;left:"+(e.clientX-r.left-s/2)+"px;top:"+(e.clientY-r.top-s/2)+"px";
    b.appendChild(el);setTimeout(function(){el.remove()},650);
  },{passive:true});
  // 2) scroll reveal for cards/buttons/list rows (staggered)
  var SEL=".game-card,.quick-cabinet-btn,.mkt-card,.section-title,#boom-players li,#history-list li,#sports-list li";
  var io="IntersectionObserver" in window&&!reduce?new IntersectionObserver(function(es){
    es.forEach(function(en){if(en.isIntersecting){en.target.classList.add("in");io.unobserve(en.target)}});
  },{threshold:.08}):null;
  function scan(root){
    if(!io)return;var i=0;
    (root||document).querySelectorAll(SEL).forEach(function(n){
      if(n.dataset.rv)return;n.dataset.rv=1;n.classList.add("reveal");
      n.style.setProperty("--d",(i++%8)*45+"ms");io.observe(n);
    });
  }
  // 3) active bottom-nav tab follows page
  function syncNav(){
    var p=document.querySelector(".page.active");if(!p)return;
    var id=(p.id||"").replace(/^page-/,"");
    document.querySelectorAll("#bottom-nav button").forEach(function(b){
      b.classList.toggle("active",b.dataset.page===id);
    });
  }
  function boot(){
    scan();syncNav();
    new MutationObserver(function(m){scan();syncNav()}).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:["class"]});
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();
