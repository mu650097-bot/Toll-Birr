// Usage: node wins_cover_check.js <win game keys...>  -> every key must resolve to a lobby page and get a cover picture (PROBLEMS: 0 for all real keys).
const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync('app.js','utf8');
const gm=app.match(/const GAMES = (\[[\s\S]*?\n\]);/)[1];
const el=()=>new Proxy(function(){},{get:(t,k)=>k==='style'?{setProperty(){},removeProperty(){}}:k==='classList'?{add(){},remove(){},toggle(){},contains(){return false}}:k==='querySelector'||k==='querySelectorAll'?()=>[]:el(),apply:()=>el(),set:()=>true});
const ctx={console,setTimeout,setInterval:()=>0,clearInterval(){},requestAnimationFrame(f){},MutationObserver:class{observe(){}},
 document:{getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},createElement:()=>el(),body:el(),readyState:'complete',head:el(),documentElement:el()},
 localStorage:{getItem(){},setItem(){}},navigator:{}};
ctx.window=ctx; ctx.self=ctx;
vm.createContext(ctx);
vm.runInContext('var GAMES='+gm+'; var goToPage=function(){}; var haptic=function(){};',ctx);
vm.runInContext(fs.readFileSync('kdm_covers.js','utf8'),ctx);
try{vm.runInContext(fs.readFileSync('game_catalog.js','utf8'),ctx);}catch(e){console.log('catalog load err',e.message)}
// resolveWinGame from app.js
const rw=app.match(/const WIN_GAME_ALIAS[\s\S]*?\n}\n/)[0];
vm.runInContext(rw.replace(/^const /,'var ')+';var resolveWinGame=resolveWinGame;',ctx);
const keys=process.argv.slice(2);
let bad=0;
for(const k of keys){
  const gk=ctx.resolveWinGame(k);
  const cv=ctx.kdmCover(gk||k,'🎉');
  const kind=!cv?'NONE':cv.startsWith('data:image/jpeg')?'ART':'svg';
  if(kind==='NONE'||!gk) {bad++;}
  console.log(k.padEnd(20),'page=',(gk||'(lobby)').padEnd(18),kind);
}
console.log('PROBLEMS:',bad);
