const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/text-studio.js'),'utf8').replace(/^export /gm,'');
function harness(edit){
  const scope=vm.createContext({document:{},TextDecoder,setTimeout:()=>1,clearTimeout(){}});
  vm.runInContext(source+'\nglobalThis.api={TextStudio,textStyle};',scope);
  let project={id:'p',manual:{text_clips:[{id:'text_a',kind:'title',text:'Title',start:1,end:4,scale:100,style:'bold',position:'center'}]},draft:{},settings:{}};
  const studio=Object.create(scope.api.TextStudio.prototype);
  const recovery={hidden:true},replace={checked:false};
  Object.assign(studio,{projectId:'p',selected:'text_a',pending:new Map(),overrides:new Map(),dragOverrides:new Map(),saving:null,importing:false,
    root:{querySelector:s=>s==='[data-replace]'?replace:recovery},status:{textContent:''},render(){},renderList(){},
    options:{project:()=>project,duration:()=>10,time:()=>2,busy:()=>false,preview(){},edit:edit||(async(action,patch)=>{project.manual.text_clips[0]={...project.manual.text_clips[0],...patch};return project;})}
  });
  return {studio,scope,setProject:p=>project=p,project:()=>project,replace};
}
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};};
test('typed text previews immediately and saves without a separate confirmation',async()=>{
  const h=harness();h.studio.queueClip('text_a',{text:'שלום world'});
  assert.equal(h.studio.clips()[0].text,'שלום world');assert.equal(h.studio.dirty(),true);
  assert.equal(await h.studio.flush(),true);assert.equal(h.project().manual.text_clips[0].text,'שלום world');assert.equal(h.studio.dirty(),false);
});
test('typing during an in-flight save retains and commits the newest value',async()=>{
  const first=deferred(),calls=[];const h=harness(async(a,p)=>{calls.push(p);return calls.length===1?first.promise:{id:'p'};});
  h.studio.queueClip('text_a',{text:'first'});const saved=h.studio.flush();
  h.studio.queueClip('text_a',{text:'second'});first.resolve({id:'p'});
  assert.equal(await saved,true);assert.equal(calls.length,2);assert.equal(calls[1].text,'second');assert.equal(h.studio.pending.size,0);
});
test('failed save retains recoverable draft and prevents selection/navigation loss',async()=>{
  const h=harness(async()=>null);h.studio.queueClip('text_a',{text:'unsaved'});
  assert.equal(await h.studio.flush(),false);assert.equal(h.studio.dirty(),true);assert.equal(h.studio.clips()[0].text,'unsaved');
  assert.equal(await h.studio.select('text_other'),false);assert.equal(h.studio.selected,'text_a');
});
test('invalid bounds and size never reach server',async()=>{
  for(const patch of [{start:NaN},{end:11},{start:4},{text:' '},{scale:151},{scale:100.5}]){
    let calls=0;const h=harness(async()=>{calls++;return{id:'p'};});h.studio.queueClip('text_a',patch);
    assert.equal(await h.studio.flush(),false);assert.equal(calls,0);
  }
});
test('drag preview cancellation does not discard a pending text edit',()=>{
  const h=harness();h.studio.queueClip('text_a',{text:'draft'});h.studio.previewClip('text_a',{start:2});
  assert.equal(h.studio.clips()[0].start,2);h.studio.previewClip('text_a',null);
  assert.equal(h.studio.clips()[0].start,1);assert.equal(h.studio.clips()[0].text,'draft');
});
test('subtitle import rejects oversized, wrong-extension and invalid UTF-8 files',async()=>{
  let calls=0;const h=harness(async()=>{calls++;return{id:'p'};});
  for(const file of [{name:'x.srt',size:1024*1024+1},{name:'x.exe',size:20},{name:'x.srt',size:2,arrayBuffer:async()=>new Uint8Array([0xff,0xff]).buffer}])await h.studio.importFile(file);
  assert.equal(calls,0);assert.equal(h.studio.importing,false);
});
test('subtitle import uses explicit replace choice and restores controls',async()=>{
  let request;const h=harness(async(a,p)=>{request={a,p};return{id:'p'};});h.replace.checked=true;
  const body=new TextEncoder().encode('WEBVTT\n\n00:00.000 --> 00:01.000\nHello');
  await h.studio.importFile({name:'captions.VTT',size:body.length,arrayBuffer:async()=>body.buffer});
  assert.equal(request.a,'text_import');assert.equal(request.p.format,'vtt');assert.equal(request.p.replace,true);assert.equal(h.studio.importing,false);
});
test('file reading never imports into a different project',async()=>{
  const read=deferred();let calls=0;const h=harness(async()=>{calls++;});
  const importing=h.studio.importFile({name:'x.srt',size:5,arrayBuffer:()=>read.promise});
  await Promise.resolve();await Promise.resolve();h.setProject({id:'another',manual:{},draft:{}});read.resolve(new TextEncoder().encode('hello').buffer);
  await importing;assert.equal(calls,0);
});
test('text preview typography uses output-relative sizes for vertical and landscape exports',()=>{
  const {scope}=harness();const style=scope.api.textStyle({scale:100,style:'bold'},1080,1920,384);
  assert.equal(style.font,14.4);assert.equal(style.stroke,1.2000000000000002);assert.equal(style.margin,28.8);
  const wide=scope.api.textStyle({scale:150,style:'clean'},1920,1080,216);assert.equal(wide.font,13.600000000000001);
});

function selectionHarness(edit){
  const h=harness(edit),removed=[];
  h.studio.root.querySelectorAll=()=>[];h.studio.inspector={hidden:false};
  h.studio.render=h.scope.api.TextStudio.prototype.render;
  h.studio.options.selectionRemoved=id=>removed.push(id);
  return {...h,removed};
}

test('successful text removal clears the inspector and timeline selection exactly once',async()=>{
  const h=selectionHarness(async()=>{h.project().manual.text_clips=[];return h.project();});
  await h.studio.action('text_remove',{clip_id:'text_a'});
  h.studio.render();
  assert.equal(h.studio.selected,null);assert.equal(h.studio.inspector.hidden,true);
  assert.deepEqual(h.removed,['text_a']);
});

test('replacing imported captions clears a missing selection but appending preserves it',async()=>{
  for(const replace of [false,true]){
    const h=selectionHarness(async()=>{if(replace)h.project().manual.text_clips=[];return h.project();});
    h.replace.checked=replace;
    const body=new TextEncoder().encode('WEBVTT\n\n00:00.000 --> 00:01.000\nHello');
    await h.studio.importFile({name:'x.vtt',size:body.length,arrayBuffer:async()=>body.buffer});
    assert.equal(h.studio.selected,replace?null:'text_a');
    assert.deepEqual(h.removed,replace?['text_a']:[]);
  }
});

test('project navigation drops a text selection before the next editor is shown',()=>{
  const h=selectionHarness();h.setProject({id:'another',manual:{text_clips:[]},draft:{}});h.studio.render();
  assert.equal(h.studio.selected,null);assert.equal(h.studio.inspector.hidden,true);
  assert.deepEqual(h.removed,['text_a']);
});

function templateHarness(){
  const h=harness(),fields=[{dataset:{templateField:'subtext'}},{dataset:{templateField:'position'}}];
  const buttons=['plain','lower_third','chapter','callout','highlight'].map(id=>({dataset:{templateChoice:id},disabled:false,
    attributes:{},setAttribute(key,value){this.attributes[key]=value;},focus(){this.focused=true;},closest(){return this;}}));
  h.studio.root.querySelectorAll=()=>fields;
  h.studio.templatePicker={querySelectorAll:()=>buttons};h.studio.templateDescription={textContent:''};
  h.scope.document.documentElement={dir:'ltr'};
  return {...h,fields,buttons};
}

test('template choice previews and saves the selected template without changing text timing or size',async()=>{
  const h=templateHarness();
  assert.equal(h.studio.chooseTemplate('lower_third'),true);
  assert.equal(h.studio.clips()[0].template,'lower_third');
  assert.equal(h.studio.clips()[0].text,'Title');assert.equal(h.studio.clips()[0].start,1);assert.equal(h.studio.clips()[0].end,4);assert.equal(h.studio.clips()[0].scale,100);
  assert.equal(h.buttons[1].attributes['aria-checked'],'true');assert.equal(h.buttons[1].tabIndex,0);
  assert.equal(h.fields[0].hidden,false);assert.equal(h.fields[1].hidden,true);
  assert.match(h.studio.templateDescription.textContent,/fixed at the lower left/);
  assert.equal(await h.studio.flush(),true);assert.equal(h.project().manual.text_clips[0].template,'lower_third');
});

test('template controls expose the actual fixed or adjustable layout and second-line support',()=>{
  const h=templateHarness();
  for(const [id,subtext,position] of [['plain',false,true],['lower_third',true,false],['chapter',true,false],['callout',false,false],['highlight',false,true]]){
    h.studio.renderTemplates(id);
    assert.equal(h.fields[0].hidden,!subtext,id);assert.equal(h.fields[1].hidden,!position,id);
    assert.equal(h.buttons.filter(button=>button.tabIndex===0).length,1);
    assert.equal(h.buttons.find(button=>button.tabIndex===0).dataset.templateChoice,id);
  }
});

test('automatic template saves keep keyboard controls focusable and queue the next choice',async()=>{
  const h=templateHarness(),first=deferred(),calls=[];
  h.studio.options.edit=async(action,patch)=>{calls.push(patch);if(calls.length===1)await first.promise;h.project().manual.text_clips[0]={...h.project().manual.text_clips[0],...patch};return h.project();};
  h.studio.chooseTemplate('lower_third');const saving=h.studio.flush();
  h.studio.options.busy=()=>true;h.studio.renderTemplates('lower_third');
  assert.ok(h.buttons.every(button=>!button.disabled));
  assert.equal(h.studio.chooseTemplate('chapter'),true);assert.equal(h.studio.clips()[0].template,'chapter');
  first.resolve();assert.equal(await saving,true);assert.equal(calls.length,2);assert.equal(h.project().manual.text_clips[0].template,'chapter');
});

test('template actions are unavailable without a draft or selection and during active work',()=>{
  for(const setup of [h=>{h.project().draft=null;},h=>{h.studio.selected=null;},h=>{h.studio.importing=true;},h=>{h.studio.options.busy=()=>true;}]){
    const h=templateHarness();setup(h);h.studio.renderTemplates('plain');
    assert.ok(h.buttons.every(button=>button.disabled));assert.equal(h.studio.chooseTemplate('chapter'),false);assert.equal(h.studio.pending.size,0);
  }
  const h=templateHarness();assert.equal(h.studio.chooseTemplate('unsupported'),false);assert.equal(h.studio.pending.size,0);
});

test('template keyboard navigation wraps, supports Home/End and respects RTL',()=>{
  const h=templateHarness();
  function key(value,index){let prevented=false;h.studio.templateKeydown({key:value,target:h.buttons[index],preventDefault(){prevented=true;}});return prevented;}
  assert.equal(key('ArrowLeft',0),true);assert.equal(h.studio.clips()[0].template,'highlight');assert.equal(h.buttons[4].focused,true);
  key('Home',4);assert.equal(h.studio.clips()[0].template,'plain');
  key('End',0);assert.equal(h.studio.clips()[0].template,'highlight');
  h.scope.document.documentElement.dir='rtl';key('ArrowRight',0);assert.equal(h.studio.clips()[0].template,'highlight');
  h.studio.options.busy=()=>true;h.studio.renderTemplates('highlight');assert.equal(key('ArrowLeft',4),false);
});

test('text inspector explains an empty selection and an unavailable edit without hiding the library',()=>{
  const h=selectionHarness();h.studio.emptySelection={};h.studio.selected=null;
  h.studio.render();assert.equal(h.studio.inspector.hidden,true);assert.equal(h.studio.emptySelection.hidden,false);assert.match(h.studio.emptySelection.textContent,/Select custom text/);
  h.project().draft=null;h.studio.render();assert.match(h.studio.emptySelection.textContent,/Create an edit/);
});
