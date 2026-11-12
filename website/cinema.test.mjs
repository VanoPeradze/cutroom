import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const source=readFileSync(new URL('./public/cinema.js',import.meta.url),'utf8');
const html=readFileSync(new URL('./public/index.html',import.meta.url),'utf8');
const common=readFileSync(new URL('./public/styles.css',import.meta.url),'utf8');
const finish=readFileSync(new URL('./public/studio.css',import.meta.url),'utf8');
function harness({reduced=false,width=1440,contextAvailable=true,canvasAvailable=true}={}) {
 let frames=0,cancels=0,draws=0,scheduled,mutation,intersection,resize,preferenceChange;
 const events={};const preference={matches:reduced,addEventListener(k,fn){preferenceChange=fn;}};
 const field={classList:{add(){}},getBoundingClientRect:()=>({width,height:850})};
 const context={clearRect(){draws++;},setTransform(){},moveTo(){},lineTo(){},closePath(){},beginPath(){},fill(){},stroke(){},createLinearGradient:()=>({addColorStop(){}})};
 const canvas={closest:()=>field,getContext:()=>contextAvailable?context:null};
 const root={dataset:{motion:reduced?'paused':'running'}};
 const document={documentElement:root,hidden:false,getElementById:()=>canvasAvailable?canvas:null,addEventListener(k,fn){events[k]=fn;}};
 class IntersectionObserver{constructor(cb){intersection=cb;}observe(){}}
 class ResizeObserver{constructor(cb){resize=cb;}observe(){}}
 class MutationObserver{constructor(cb){mutation=cb;}observe(){}}
 const window={matchMedia:()=>preference,devicePixelRatio:3,IntersectionObserver,ResizeObserver,addEventListener(){}};
 runInNewContext(source,{document,window,IntersectionObserver,ResizeObserver,MutationObserver,requestAnimationFrame(fn){frames++;scheduled=fn;return frames;},cancelAnimationFrame(){cancels++;}});
 return {document,root,canvas,preference,events,get frames(){return frames;},get cancels(){return cancels;},get draws(){return draws;},tick:t=>scheduled(t),mutate:()=>mutation(),intersect:v=>intersection([{isIntersecting:v}]),resize:()=>resize(),preferenceChange:()=>preferenceChange()};
}
test('film field is decorative, local and not required for content or downloads',()=>{
 assert.match(html,/<div class="film-field" aria-hidden="true">/);
 assert.match(html,/<canvas id="filmField"><\/canvas>/);
 assert.match(html,/id="heroMotionToggle"[\s\S]*?data-motion-state/);
 assert.match(html,/Mac source launcher, not a signed app/);
 assert.doesNotMatch(source,/fetch\s*\(|localStorage|setInterval|WebGL|addEventListener\(['"](?:mouse|pointer)/);
 assert.doesNotMatch(html,/class="eyebrow"|lucide|🚀|⚡/i);
 assert.doesNotMatch(common+finish,/monospace|JetBrains|Courier|#(?:00ff00|39ff14|ccff00)\b/i);
 assert.match(finish,/\.film-static/);
 assert.match(finish,/@media\(prefers-reduced-motion:reduce\)/);
});
test('canvas is capped, pauses offscreen and resumes without double loops',()=>{
 const h=harness();assert.equal(h.frames,1);assert.equal(h.canvas.width,2160);assert.ok(h.draws>0);
 h.intersect(false);assert.equal(h.cancels,1);const stopped=h.frames;
 h.intersect(true);assert.equal(h.frames,stopped+1);
 h.root.dataset.motion='paused';h.mutate();const paused=h.frames;
 h.tick(100);assert.equal(h.frames,paused,'A stale callback cannot start another animation');
 h.root.dataset.motion='running';h.mutate();assert.equal(h.frames,paused+1);
 h.document.hidden=true;h.events.visibilitychange();const hidden=h.frames;
 h.document.hidden=false;h.events.visibilitychange();assert.equal(h.frames,hidden+1);
});
test('reduced-motion draws a static scene without scheduling animation',()=>{
 const h=harness({reduced:true});assert.equal(h.frames,0);assert.ok(h.draws>0);
 h.root.dataset.motion='running';h.mutate();assert.equal(h.frames,0,'Device preference takes priority');
 h.preference.matches=false;h.preferenceChange();assert.equal(h.frames,1);
});
test('mobile backing resolution is bounded and missing canvas is harmless',()=>{
 const h=harness({width:390});assert.equal(h.canvas.width,488);
 assert.equal(harness({contextAvailable:false}).frames,0);
 assert.equal(harness({canvasAvailable:false}).frames,0);
});


test('the screening room preserves the owner-requested purple/cyan brand',()=>{
 assert.match(common,/--cyan:#70d9e0;/);
 assert.match(common,/--violet:#b7a6de;/);
 assert.match(finish,/\.hero h1 span\+span\{color:var\(--violet\)\}/);
 assert.match(source,/\[112,217,224\]:\[183,166,222\]/);
 assert.doesNotMatch(common+finish+source,/#efb28d|#f9c4a4|225,162,127|244,217,195/);
 const luminance=hex=>hex.replace('#','').match(/../g).map(c=>parseInt(c,16)/255)
  .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
  .reduce((total,v,i)=>total+v*[.2126,.7152,.0722][i],0);
 const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
 for(const [foreground,background]of [
  ['#181c2a','#70d9e0'],['#181c2a','#9ae8ed'],['#b7a6de','#15151f'],
  ['#b1adc3','#15151f'],['#57506b','#f0eff7'],['#624184','#f0eff7'],
  ['#181c2a','#b7a6de'],['#49365f','#b7a6de'],
 ])assert.ok(contrast(foreground,background)>=4.5,foreground+' on '+background);
});
