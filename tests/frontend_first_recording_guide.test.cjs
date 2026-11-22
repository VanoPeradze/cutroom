const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../web/first-recording-guide.js'),'utf8');
const {needsFirstRecording,initFirstRecordingGuide}=new Function(src.replace(/^export /gm,'')+';return {needsFirstRecording,initFirstRecordingGuide}')();
const manual=(id='p')=>({id,settings:{workflow:'manual'},sources:{A:null,B:null},draft:null});
function harness(){
  const node=()=>{const listeners={};return{dataset:{},hidden:false,disabled:false,textContent:'',value:'',files:[],listeners,clicked:0,addEventListener(t,f){(listeners[t]||=[]).push(f)},removeEventListener(t,f){listeners[t]=listeners[t].filter(x=>x!==f)},emit(t,e={}){for(const f of listeners[t]||[])f(e)},click(){this.clicked++},contains(n){return n===this}}};
  const root=node(),choose=node(),picker=node(),status=node(),s={project:manual(),open:true,view:1,busy:false,retained:false},calls=[];
  root.querySelector=k=>k.includes('choose')?choose:k.includes('file')?picker:status;
  let resolve,reject; const c=initFirstRecordingGuide(root,{snapshot:()=>s,importFiles:files=>{calls.push(files);return new Promise((r,j)=>{resolve=r;reject=j})},notice:()=>'Pick a video first.'});
  const file=(name='scene.mp4')=>({name,type:'video/mp4'});
  const drag=(t,files=[file()],types=['Files'])=>{const e={dataTransfer:{files,types},preventDefault(){this.prevented=true},stopPropagation(){this.stopped=true}};root.emit(t,e);return e};
  return{s,root,choose,picker,status,c,calls,drag,file,finish:x=>resolve(x),fail:x=>reject(x)};
}
const idle=()=>new Promise(r=>setImmediate(r));
test('only a new manual timeline without source, draft, retained data or sequence is eligible',()=>{
  const p=manual();assert.equal(needsFirstRecording(p,true),true);
  for(const [project,open,retained] of [[p,false,false],[null,true,false],[{...p,id:''},true,false],[p,true,true],[{...p,settings:{workflow:'ai'}},true,false],[{...p,draft:{}},true,false],[{...p,editor_sequence:{}},true,false],[{...p,sources:{A:{}}},true,false],[{...p,sources:{B:{}}},true,false]])assert.equal(needsFirstRecording(project,open,retained),false);
});
test('picker delegates exactly once, blocks repeat input during import and displays native validation errors',async()=>{
  const h=harness();h.choose.emit('click');assert.equal(h.picker.clicked,1);h.picker.files=[h.file()];h.picker.emit('change');
  assert.equal(h.calls.length,1);assert.equal(h.choose.disabled,true);assert.match(h.status.textContent,/Importing/);h.choose.emit('click');h.drag('drop');assert.equal(h.picker.clicked,1);assert.equal(h.calls.length,1);
  h.finish(null);await idle();assert.equal(h.status.textContent,'Pick a video first.');assert.equal(h.choose.disabled,false);
});
test('cancelled and stale-project chooser never write, including a same-ID reopen with a new view token',()=>{
  const h=harness();h.choose.emit('click');h.picker.emit('cancel');h.picker.files=[h.file()];h.picker.emit('change');assert.equal(h.calls.length,0);
  h.choose.emit('click');h.s.project=manual('next');h.c.sync();h.picker.files=[h.file()];h.picker.emit('change');assert.equal(h.calls.length,0);
  h.choose.emit('click');h.s.view++;h.picker.files=[h.file()];h.picker.emit('change');assert.equal(h.calls.length,0);
});
test('only OS file drops are accepted; blocked drops suppress navigation without making an import',async()=>{
  const h=harness();assert.equal(h.drag('dragover',[],['text/plain']).prevented,undefined);assert.equal(h.drag('drop',[],['text/uri-list']).prevented,undefined);
  h.s.busy=true;assert.equal(h.drag('dragover').dataTransfer.dropEffect,'none');assert.equal(h.drag('drop').prevented,true);assert.equal(h.calls.length,0);
  h.s.busy=false;assert.equal(h.drag('dragenter').dataTransfer.dropEffect,'copy');assert.equal(h.root.dataset.dragging,'true');
  const files=[h.file('a.mp4'),h.file('b.mp4')];h.drag('drop',files);assert.deepEqual(h.calls,[files]);assert.equal(h.root.dataset.dragging,undefined);
  h.finish({items:[{status:'failed',message:'Format is not supported.'}]});await idle();assert.equal(h.status.textContent,'Format is not supported.');
});
test('closing or populating the editor drops stale status and leaves the real monitor alone',async()=>{
  const h=harness();h.drag('drop');h.s.project=manual('other');h.s.view++;h.c.sync();h.fail(new Error('old error'));await idle();
  assert.equal(h.status.textContent,'');assert.equal(h.choose.disabled,false);h.s.project.sources.A={};h.c.sync();assert.equal(h.root.hidden,true);
  h.s.project=manual();h.s.open=false;h.c.sync();assert.equal(h.root.hidden,true);h.c.destroy();h.choose.emit('click');assert.equal(h.picker.clicked,0);
});
