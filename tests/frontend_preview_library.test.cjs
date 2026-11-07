const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname,'../web');
class Element {
 constructor(tag='div') { this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.listeners={};this.value='';this.textContent=''; }
 appendChild(e) { e.remove();this.children.push(e);e.parentNode=this;return e; }
 append(...es) { es.forEach(e=>this.appendChild(e)); }
 insertBefore(e,b) { e.remove();const i=this.children.indexOf(b);this.children.splice(i<0?this.children.length:i,0,e);e.parentNode=this; }
 remove() { if(this.parentNode) {this.parentNode.children=this.parentNode.children.filter(e=>e!==this);this.parentNode=null;} }
 setAttribute(k,v) {this.attrs[k]=v;}
 addEventListener(k,f) {this.listeners[k]=f;}
 click() {this.listeners.click?.();}
 after(e) {this.parentNode.appendChild(e);}
}
test('viewport isolates sizing while retaining the exact media node, and restores DOM order',async()=>{
 const {initPreviewViewport}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync(path.join(web,'workspace.js'),'utf8')).toString('base64'));
 const preview=new Element(),stage=new Element(),controls=new Element(),notice=new Element(),video=new Element('video');video.currentTime=13.5;stage.append(video);preview.append(stage,controls,notice);
 const doc={getElementById:()=>stage,createElement:tag=>new Element(tag)};
 const handle=initPreviewViewport({document:doc,preview});
 assert.equal(preview.children[0].className,'preview-viewport');assert.equal(preview.children[0].children[0],stage);assert.equal(stage.children[0],video);assert.equal(video.currentTime,13.5);
 initPreviewViewport({document:doc,preview});assert.equal(preview.children.length,3);
 handle.restore();assert.deepEqual(preview.children,[stage,controls,notice]);assert.equal(video.currentTime,13.5);
});
test('media view toggles reuse cards, preserve filters and survive denied preference storage',()=>{
 const script=fs.readFileSync(path.join(web,'studio-screens.js'),'utf8');
 const section=script.slice(script.indexOf('  function initMedia() {'),script.indexOf('  // ---------- Layout ----------'));
 for(const blocked of [false,true]) {
  const shelf=new Element(),heading=new Element(),title=new Element(),cards=[new Element(),new Element()];
  cards[0].dataset.kind='video';cards[0].textContent='Camera B.mp4';cards[1].dataset.kind='audio';cards[1].textContent='Music.wav';
  shelf.append(heading,...cards);let stored='grid';
  const context={$: (q)=>q==='#studioShelfMedia'?shelf:q==='.shelf-heading'?heading:q==='h3'?title:null,$$:()=>cards,make:(tag,cls,text)=>{const e=new Element(tag);e.className=cls;e.textContent=text||'';return e;},syncers:new Set(),observe(){},localStorage:{getItem(){if(blocked)throw Error('Denied');return stored;},setItem(k,v){if(blocked)throw Error('Denied');stored=v;}}};
  vm.runInNewContext(section+'\ninitMedia();',context);
  const tools=shelf.children.at(-1),[search,filters,views]=tools.children;
  assert.equal(shelf.dataset.libraryView,blocked?'list':'grid');
  for(const view of ['list','grid','list']) {views.children.find(b=>b.dataset.view===view).click();assert.equal(shelf.dataset.libraryView,view);assert.equal(views.children.filter(b=>b.attrs['aria-pressed']==='true').length,1);}
  search.value='camera';search.listeners.input();assert.equal(cards[0].hidden,false);assert.equal(cards[1].hidden,true);
  views.children[1].click();assert.equal(cards[1].hidden,true);
  search.value='';filters.children.find(b=>b.dataset.value==='audio').click();assert.equal(cards[0].hidden,true);assert.equal(cards[1].hidden,false);
  assert.equal(shelf.children[1],cards[0]);assert.equal(shelf.children[2],cards[1]);
 }
});
