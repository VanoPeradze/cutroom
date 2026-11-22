import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const src = readFileSync(new URL('./public/reel.js',import.meta.url),'utf8');
const html = readFileSync(new URL('./public/index.html',import.meta.url),'utf8');
function node(data={}) {
  return {dataset:{...data},children:[],attrs:{},events:{},hidden:false,value:'',textContent:'',
    addEventListener(k,fn){this.events[k]=fn;},setAttribute(k,v){this.attrs[k]=v;},
    removeAttribute(k){delete this.attrs[k];},append(...items){this.children.push(...items);},
    querySelector(sel){return this.children.find(c=>'.'+c.className===sel);},
    click(){this.events.click?.();}};
}
function fixture({reduced=false}={}) {
 const el=Object.fromEntries(['night-drive','reel-play','reel-play-label','reel-seek','shot-number','reel-time'].map(id=>[id,node()]));
 const r=el['night-drive'],root=Object.assign(node({motion:reduced?'paused':'running'}),{lang:'en'});
 const track=node(),tools=node(),modes=['journey','flashback'].map(mode=>node({mode}));
 const imgs=['pass','crossing','lake'].map(still=>node({still}));
 r.querySelector=s=>({'.reel-tools':tools,'.reel-track':track}[s]);r.querySelectorAll=s=>({'[data-mode]':modes,'[data-still]':imgs}[s]);
 const pref=Object.assign(node(),{matches:reduced}), win=node();
 let observer,intersect,now=0,id=0;const pending=new Map();
 class MutationObserver {constructor(cb){observer=cb;}observe(){}}
 class IntersectionObserver {constructor(cb){intersect=cb;}observe(){}}
 win.IntersectionObserver=IntersectionObserver;win.matchMedia=()=>pref;
 const document=Object.assign(node(),{documentElement:root,hidden:false,getElementById:id=>el[id],createElement:()=>node()});
 runInNewContext(src,{document,window:win,MutationObserver,IntersectionObserver,performance:{now:()=>now},requestAnimationFrame:cb=>{pending.set(++id,cb);return id;},cancelAnimationFrame:key=>pending.delete(key)});
 return {r,root,el,track,tools,modes,imgs,pref,document,pending,get button(){return el['reel-play'];},get slider(){return el['reel-seek'];},
  advance(ms){now+=ms;const frames=[...pending.values()];pending.clear();for(const cb of frames)cb(now);},
  seek(n){el['reel-seek'].value=String(n);el['reel-seek'].events.input();},
  mutate(k,v){observer([{attributeName:k,oldValue:v}]);},intersect(v){intersect([{isIntersecting:v}]);}};
}
test('static poster and each original scene are local; optional controls enhance on success',()=>{
 assert.match(html,/<div class="reel-tools" hidden>/);
 for(const id of ['pass','crossing','lake']) {
  const svg=readFileSync(new URL('./public/assets/night-drive-'+id+'.svg',import.meta.url),'utf8');
  assert.match(svg,/viewBox="0 0 960 540"/);assert.doesNotMatch(svg,/<script|<image|<foreignObject|\bhref\s*=/i);
  assert.match(html,new RegExp('data-still="'+id+'"[^>]*data-he-alt='));
 }
 const h=fixture();assert.equal(h.tools.hidden,false);assert.equal(h.pending.size,0);
 assert.deepEqual(h.imgs.map(x=>x.hidden),[false,true,true]);assert.equal(h.track.children.length,3);
 assert.doesNotMatch(src,/fetch\s*\(|localStorage|new Audio|setInterval/);
});
test('hard cuts use half-open boundaries; end holds the last shot and starts from zero on replay',()=>{
 const h=fixture();const first=h.track.children[0];h.button.click();assert.equal(h.pending.size,1);
 h.advance(2999);assert.equal(h.r.dataset.shot,'pass');h.advance(1);assert.equal(h.r.dataset.shot,'crossing');
 h.advance(2000);assert.equal(h.r.dataset.shot,'lake');h.advance(3000);
 assert.equal(h.slider.value,'8');assert.equal(h.r.dataset.playing,'false');assert.equal(h.pending.size,0);
 h.button.click();assert.equal(h.slider.value,'0');assert.equal(h.r.dataset.shot,'pass');h.button.click();
 assert.equal(h.track.children[0],first);assert.equal(h.pending.size,0);
});
test('changing edit resets and pauses; its reordered track and scrubber point at the same illustrated shot',()=>{
 const h=fixture();h.button.click();h.advance(250);h.modes[1].click();
 assert.equal(h.pending.size,0);assert.equal(h.slider.value,'0');assert.equal(h.r.dataset.shot,'lake');
 assert.deepEqual(h.track.children.map(b=>b.dataset.clip),['lake','pass','crossing']);
 h.track.children[1].click();assert.equal(h.slider.value,'2');h.seek(6.4);assert.equal(h.r.dataset.shot,'pass');
 h.seek(6.5);assert.equal(h.r.dataset.shot,'crossing');h.seek(50);assert.equal(h.slider.value,'8');
 assert.equal(h.track.children[2].attrs['aria-current'],'step');assert.equal(h.track.children[1].attrs['aria-current'],undefined);
});
test('language, visibility, reduced motion, rapid toggles and seek preserve manual control',()=>{
 const h=fixture({reduced:true});h.modes[1].click();h.seek(2.2);h.root.lang='he';h.mutate('lang','en');
 assert.match(h.slider.attrs['aria-valuetext'],/שניות/);assert.equal(h.slider.value,'2.2');
 const old=h.track.children[1];for(let i=0;i<5;i++)h.button.click();assert.equal(h.pending.size,1);
 h.intersect(false);assert.equal(h.pending.size,0);h.intersect(true);assert.equal(h.pending.size,0);
 h.button.click();h.document.hidden=true;h.document.events.visibilitychange();assert.equal(h.r.dataset.playing,'false');
 h.document.hidden=false;h.button.click();h.seek(4);assert.equal(h.pending.size,0);assert.equal(h.r.dataset.shot,'pass');
 assert.equal(h.track.children[1],old);
});
