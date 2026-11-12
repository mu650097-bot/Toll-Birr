const fs=require('fs');const src=fs.readFileSync(__dirname+'/kdm_boom.js','utf8');
const a=src.indexOf('  var FUSE_SEC'), b=src.indexOf('  function say(root');
const body=src.slice(a,b);
let log=[], ticks=[];
global.setInterval=(f)=>{ticks.push(f);return ticks.length;}; global.clearInterval=(id)=>{ticks[id-1]=null;};
global.document={body:{contains:()=>true}};
const el={hidden:true,textContent:'',classList:{toggle(){}}};
const root={querySelector:()=>el};
const S={round:null,busy:false,fuseLeft:10,fuseFor:'',fuseT:0};
const $=(r,s)=>r.querySelector(s);
const say=(...a)=>log.push('say');const cash=()=>log.push('cash');const pick=(r,i)=>log.push('pick'+(i>=0&&i<3?'ok':'bad'));
eval(body+';globalThis.fuse=fuse;globalThis.fuseStop=fuseStop;');
const run=(n)=>{for(let i=0;i<n;i++){const f=ticks[S.fuseT-1];if(f)f();}};
const ok=(c,m)=>{if(!c){console.log('FAIL',m);process.exit(1)}};
// 1) no round -> hidden
fuse(root); ok(el.hidden===true,'hidden w/o round');
// 2) round, progress 0 -> shown 00:10; after 10 ticks picks random box
S.round={id:1,progress:0}; fuse(root); ok(!el.hidden&&el.textContent==='Fuse 00:10','start 10');
run(4); ok(el.textContent==='Fuse 00:06','counts down'); run(6); ok(log.join()==='pickok','auto pick at 0 with no safe level: '+log);
// 3) progress>=1 -> auto cash out
log=[];S.fuseT=0;S.round={id:1,progress:2};S.fuseFor='';fuse(root);run(10);ok(log.join()==='say,cash','auto cashout: '+log);
// 4) new level resets timer
log=[];S.fuseT=0;S.round={id:2,progress:1};S.fuseFor='';fuse(root);run(5);S.round.progress=2;fuse(root);ok(el.textContent==='Fuse 00:10','reset on new level');
// 5) busy pauses (no tick effect), round end stops
S.busy=true;fuse(root);ok(S.fuseT===0,'busy stops interval');S.busy=false;S.round=null;fuse(root);ok(el.hidden,'hidden after end');
console.log('FUSE_LOGIC=PASS');
