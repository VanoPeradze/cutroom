const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const test=require('node:test');
const plain=value=>JSON.parse(JSON.stringify(value));

function fixture(){
  const nodes=new Map();
  const node=id=>{const children=new Map();return {id,value:'',dataset:{},textContent:'',hidden:false,disabled:false,style:{setProperty(){}},
    classList:{add(){},remove(){},toggle(){}},listeners:{},setAttribute(){},addEventListener(type,handler){this.listeners[type]=handler;},scrollIntoView(){},focus(){},select(){},
    querySelector(key){if(!children.has(key))children.set(key,node(key));return children.get(key);},querySelectorAll(){return [];}};};
  const document={getElementById(id){if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id);},querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context=vm.createContext({document,console,dictionaries:{en:{}},setTimeout:()=>1,clearTimeout(){},
    window:{addEventListener(){}},requestAnimationFrame:callback=>callback(),performance:{now:()=>0}});
  const run=code=>vm.runInContext(code,context);
  for(const name of ['source-tracks.js','timeline.js','media-studio.js'])run(fs.readFileSync(path.join(__dirname,'../web',name),'utf8').replace(/^export /gm,''));
  run(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,''));
  run(`cacheElements();
    state.project={id:'context',revision:4,settings:{fps:30},sources:{A:{duration:8},B:{duration:8}},
      manual:{media_clips:[{id:'media_audio',asset_id:'sound',start:0,end:4,role:'music',volume_db:0}],text_clips:[]},
      assets:{sound:{kind:'audio',duration:4,status:'ready'}},draft:{output_duration:4},
      editor_sequence:{duration:4,sequence:{version:1,duration:4,camera_plan:[]},source_tracks:{A:[{id:'a1',start:0,end:2,source_start:0},{id:'a2',start:2,end:4,source_start:2}],
        B:[{id:'b1',start:0,end:2,source_start:1},{id:'b2',start:2,end:4,source_start:3}]}},
      editor_captions:[{id:'c1',segment_id:1,start:0,end:2,text:'Original caption'},{id:'c2',segment_id:2,start:2,end:4,text:'Next caption'}]};
    state.studio.open=true;globalThis.tabs=[];globalThis.tools=[];globalThis.actions=[];globalThis.reveals=[];globalThis.seeks=[];
    renderManualControls=renderSourceMixer=highlightTranscriptSelection=hydrateSourceMixerLayout=loadCropControls=()=>{};
    renderCaptionInspector=renderPictureSpeed=updatePreviewCaption=()=>{};
    selectAdvancedTab=tab=>tabs.push(tab);selectEditTool=tool=>tools.push(tool);
    pauseAllMedia=()=>{};previewTimelineTime=()=>1;previewPlaybackTime=()=>1;seekSourcePreview=time=>seeks.push(time);
    state.timeline={gesture:null,selection:null,mediaSelection:null,captionSelection:null,scheduleDraw(){},
      clearSelection(notify=true){this.selection=null;if(notify)setManualSelection(null);},
      selectCaption(id){this.captionSelection=id;},revealCaption(id){reveals.push(id);},
      selectRange(start,end){state.manualSelection={start,end};}};
    applyManualEdit=async(action,detail)=>{actions.push({action,detail});return state.project;};
    state.mediaStudio=Object.create(MediaStudio.prototype);
    Object.assign(state.mediaStudio,{options:{project:()=>state.project,busy:()=>false,preview(){},edit:async(action,detail)=>{
      actions.push({action,detail});state.project={...state.project,manual:{...state.project.manual,media_clips:state.project.manual.media_clips.map(clip=>clip.id===detail.clip_id?{...clip,...detail}:clip)}};return state.project;}},
      root:document.getElementById('testMediaRoot'),pending:new Map(),overrides:new Map(),players:new Map(),status:{textContent:''},render(){},renderMixer(){}});
    elements.captionItemText.value='Original caption';elements.captionItemStart.value='0';elements.captionItemEnd.value='2';
    elements.captionItemScale.value='';elements.captionItemEditor.querySelector('input[name="captionItemScope"]:checked').value='source';
  `);
  return {run,nodes};
}

test('selecting source footage from another tool reveals existing clip controls without changing Together scope',async()=>{
  const {run}=fixture();run('setManualSelection({start:0,end:2},{kind:"clip"});');await new Promise(setImmediate);
  assert.deepEqual(plain(run('tabs')),['timeline']);assert.deepEqual(plain(run('tools')),['clip']);
  assert.equal(run('activeEditTarget()'),'edit');assert.deepEqual(plain(run('state.manualSelection')),{start:0,end:2});
  assert.deepEqual(plain(run('actions')),[]);
});

test('selected imported audio opens its per-clip controls and saves only that clip volume',async()=>{
  const {run}=fixture();assert.equal(await run('selectTimelineMedia("media_audio")'),true);
  assert.deepEqual(plain(run('tabs')),['media']);assert.equal(run('state.mediaStudio.selected'),'media_audio');
  assert.equal(run('state.mediaStudio.root.querySelector(".media-clip-audio").open'),true);
  run(`state.mediaStudio.change({dataset:{media:'volume_db'},type:'range',value:'-12',hasAttribute:()=>false,checkValidity:()=>true});`);
  assert.equal(await run('state.mediaStudio.flush()'),true);
  assert.equal(run('state.project.manual.media_clips[0].volume_db'),-12);
  assert.deepEqual(plain(run('actions')),[{action:'media_update',detail:{clip_id:'media_audio',volume_db:-12}}]);
  assert.equal(run('state.project.manual.audio_mixer'),undefined,'no group mixer gain is changed');
});

test('an invalid caption draft blocks caption/media/source navigation and keeps the actual typed buffer',async()=>{
  for(const route of ['selectCaptionItem("c2")','selectTimelineMedia("media_audio")','revealSourceClipInspector()']){
    const {run}=fixture();run(`state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='';state.manualSelection={start:0,end:2};`);
    assert.equal(await run(route),false);assert.equal(run('state.captionSelection'),'c1');
    assert.equal(run('state.captionDirty'),true);assert.equal(run('elements.captionItemText.value'),'');
    assert.equal(run('state.timeline.captionSelection'),'c1');assert.deepEqual(plain(run('tabs')),[]);
    assert.deepEqual(plain(run('actions')),[]);
  }
});

test('a rejected caption API save cannot discard unsaved text or navigate to another inspector',async()=>{
  const {run}=fixture();run(`state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='Unsaved correction';applyManualEdit=async(action,detail)=>{actions.push({action,detail});return null;};`);
  assert.equal(await run('selectCaptionItem("c2")'),false);
  assert.equal(run('state.captionSelection'),'c1');assert.equal(run('state.captionDirty'),true);
  assert.equal(run('elements.captionItemText.value'),'Unsaved correction');assert.deepEqual(plain(run('tabs')),[]);
  assert.equal(run('actions[0].action'),'caption_update');
});

test('a rejected custom text flush keeps its existing selection and inspector instead of opening media',async()=>{
  const {run}=fixture();run(`state.textStudio={selected:'text_old',dirty:()=>true,flush:async()=>false};state.timeline.mediaSelection='media_audio';`);
  assert.equal(await run('selectTimelineMedia("media_audio")'),false);
  assert.equal(run('state.textStudio.selected'),'text_old');assert.equal(run('state.timeline.mediaSelection'),'text_old');
  assert.deepEqual(plain(run('tabs')),[]);assert.equal(run('state.mediaStudio.selected'),undefined);
});

test('a failed awaited text selection restores the previous layer highlight without opening the new inspector',async()=>{
  const {run}=fixture();run(`state.project.manual.text_clips=[{id:'text_next',start:0,end:2,text:'Next'}];
    state.textStudio={selected:'text_old',dirty:()=>false,select:async()=>false};state.timeline.mediaSelection='text_next';`);
  assert.equal(await run('selectTimelineMedia("text_next")'),false);
  assert.equal(run('state.timeline.mediaSelection'),'text_old');assert.deepEqual(plain(run('tabs')),[]);
});

test('timeline caption selection does not reveal or scroll during a pointer gesture; explicit open may reveal',async()=>{
  const {run}=fixture();run(`state.timeline.gesture={kind:'caption'};`);
  assert.equal(await run('selectCaptionItem("c1",{reveal:false})'),true);assert.deepEqual(plain(run('reveals')),[]);
  run('state.timeline.gesture=null;');await run('selectCaptionItem("c1",{seek:true,focus:true})');
  assert.deepEqual(plain(run('reveals')),['c1']);
});

test('B clip selection records its source explicitly before Effects follows that target',()=>{
  const {run}=fixture();run(`state.editTarget='B';state.manualSelection={start:0,end:2};renderClipTrim();
    state.chromaStudio={options:{selectedTarget:()=>state.trimClip?.slot},validSource:slot=>['A','B'].includes(slot),source:{value:'A',onchange(){actions.push({source:this.value});}}};followChromaSelection();`);
  assert.equal(run('state.trimClip.slot'),'B');assert.equal(run('state.chromaStudio.source.value'),'B');
  assert.equal(run('state.editTarget'),'B');assert.deepEqual(plain(run('actions')),[{source:'B'}]);
});

test('a delayed selection save cannot open tools in a newly loaded project',async()=>{
  const {run}=fixture();run(`globalThis.finishSave=null;state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='Correction';
    applyManualEdit=()=>new Promise(resolve=>{finishSave=resolve;});globalThis.navigation=selectTimelineMedia('media_audio');`);
  await new Promise(setImmediate);
  run(`state.project={id:'different',manual:{},draft:{output_duration:2}};finishSave(null);`);
  assert.equal(await run('navigation'),false);assert.deepEqual(plain(run('tabs')),[]);
});

test('actual timeline pointer cycles cannot start or commit another caption drag over a dirty caption draft',()=>{
  const {run}=fixture();run(`state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='';
    globalThis.testTimeline=Object.create(TimelineView.prototype);Object.assign(testTimeline,{project:state.project,canEdit:canEditTimeline,
      canvas:{style:{},focus(){}},timeFromEvent:()=>1,updatePointerCursor(){},scheduleDraw(){},releasePointer(){},snappedTime:value=>value,validateSnap(){},
      onCaptionEdit:(id,times)=>runCaptionAction('caption_update',{caption_id:id,...times})});
    globalThis.pointer={button:0,pointerId:1,clientX:20,clientY:20,preventDefault(){}};
    testTimeline.pointerDown(pointer);testTimeline.pointerMove(pointer);testTimeline.pointerUp(pointer);`);
  assert.equal(run('testTimeline.gesture == null'),true);assert.deepEqual(plain(run('actions')),[]);
  run(`testTimeline.gesture={kind:'caption',pointerId:1,caption:{id:'c2',start:0,end:2},startTime:0,clientX:0,clientY:0,dragged:true,patch:{}};
    testTimeline.pointerMove(pointer);testTimeline.pointerUp(pointer);`);
  assert.deepEqual(plain(run('actions')),[]);assert.equal(run('state.captionDirty'),true);
  assert.equal(run('elements.captionItemText.value'),'');
});

test('typing during a deferred caption save retains the newer real input buffer and blocks navigation',async()=>{
  const {run}=fixture();run(`bindCaptionItemEvents();state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='First edit';
    globalThis.finishSave=null;applyManualEdit=()=>new Promise(resolve=>{finishSave=resolve;});globalThis.navigation=selectTimelineMedia('media_audio');`);
  await new Promise(setImmediate);
  run(`elements.captionItemText.value='Newer edit while saving';elements.captionItemEditor.listeners.input();finishSave(state.project);`);
  assert.equal(await run('navigation'),false);assert.equal(run('state.captionDirty'),true);
  assert.equal(run('elements.captionItemText.value'),'Newer edit while saving');assert.equal(run('state.captionSelection'),'c1');
  assert.deepEqual(plain(run('tabs')),[]);
});

test('a successful save from an old project cannot clear the new project caption draft',async()=>{
  const {run}=fixture();run(`state.captionSelection='c1';state.captionDirty=true;elements.captionItemText.value='Old project correction';
    globalThis.oldProject=state.project;globalThis.finishSave=null;applyManualEdit=()=>new Promise(resolve=>{finishSave=resolve;});globalThis.saving=saveCaptionItem();`);
  await new Promise(setImmediate);
  run(`state.project={id:'new',editor_captions:[{id:'new-caption',text:'New original',start:0,end:1}]};state.captionSelection='new-caption';
    state.captionDirty=true;state.captionStatus='New unsaved edit';elements.captionItemText.value='New project draft';finishSave(oldProject);`);
  await run('saving');assert.equal(run('state.captionDirty'),true);assert.equal(run('state.captionSelection'),'new-caption');
  assert.equal(run('elements.captionItemText.value'),'New project draft');assert.equal(run('state.captionStatus'),'New unsaved edit');
});

test('actual layout selection keeps Layout open while a footage click reveals clip tools',async()=>{
  for(const kind of ['layout','clip']){
    const {run}=fixture();run(`globalThis.testTimeline=Object.create(TimelineView.prototype);Object.assign(testTimeline,{project:state.project,canEdit:canEditTimeline,
      canvas:{style:{}},timeFromEvent:()=>1,updatePointerCursor(){},scheduleDraw(){},releasePointer(){},
      selection:{start:0,end:2},gesture:{kind:'${kind}',pointerId:1,clientX:20,clientY:20,layout:{start:0,end:2},dragged:false},
      onSelectionChange:setManualSelection,onLayoutSelect:()=>tabs.push('framing')});state.timeline=testTimeline;
      testTimeline.pointerUp({pointerId:1,clientX:20,clientY:20});`);
    await new Promise(setImmediate);
    assert.deepEqual(plain(run('tabs')),kind==='layout'?['framing']:['timeline']);
    assert.deepEqual(plain(run('actions')),[]);
  }
});
