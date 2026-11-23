const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load() {
  const context=vm.createContext({window:{},document:{},setTimeout,clearTimeout,performance:{now:()=>0}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+
    '\nglobalThis.exports={MediaStudio,MediaImportQueue,planMediaImports}',context);
  return context.exports;
}
const {MediaStudio,MediaImportQueue,planMediaImports}=load();
const video=(name='video.mp4')=>({name,type:'video/mp4'});
const audio=(name='sound.wav')=>({name,type:'audio/wav'});
const image=(name='title.png')=>({name,type:'image/png'});
const empty=()=>({id:'one',settings:{workflow:'manual'},sources:{A:null,B:null},assets:{},draft:null});
const edit=()=>({...empty(),sources:{A:{name:'original.mp4'}},draft:{output_duration:8},
  manual:{media_clips:[]},assets:{video:{id:'video',kind:'video',status:'ready',duration:4},
    audio:{id:'audio',kind:'audio',status:'ready',duration:4},image:{id:'image',kind:'image',status:'ready'}}});
function deferred(){let resolve;const promise=new Promise(yes=>resolve=yes);return {promise,resolve};}
const names=files=>Array.from(files,file=>file.name);
const statuses=queue=>Array.from(queue.items,item=>item.status);
function studioHarness(project=edit()) {
  let current=project;
  const studio=Object.create(MediaStudio.prototype);
  Object.assign(studio,{selected:null,pending:new Map(),overrides:new Map(),players:new Map(),saving:null,uploading:false,
    status:{textContent:''},render(){},flush:async()=>true,
    options:{project:()=>current,busy:()=>false,pause(){},flushSettings:async()=>{},
      uploadFile:async()=>({}),acceptUpload:async()=>{},edit:async()=>current}});
  return {studio,activate:next=>{current=next;},project:()=>current};
}

test('empty mixed selection starts with its first video while preserving every other file and caller order',()=>{
  const files=[audio(),image(),video('first.mp4'),video('second.mp4')];
  const plan=planMediaImports(files,empty());
  assert.deepEqual(names(plan.files),['first.mp4','sound.wav','title.png','second.mp4']);
  assert.deepEqual(names(files),['sound.wav','title.png','first.mp4','second.mp4']);
  assert.equal(plan.firstSource,true);assert.match(plan.note,/first.mp4/);
});
test('existing timeline or legacy manual source keeps batch order and never chooses a replacement source',()=>{
  for(const project of [edit(),{...empty(),sources:{A:{}}}]){
    const plan=planMediaImports([audio(),video(),image()],project);
    assert.equal(plan.firstSource,false);assert.deepEqual(names(plan.files),['sound.wav','video.mp4','title.png']);
    assert.match(plan.note,/timeline stays unchanged/);
  }
});
test('unsupported empty audio/image batch and capacity overflow reject the whole selection without truncation',()=>{
  assert.throws(()=>planMediaImports([audio(),image()],empty()),/Start with a video recording/);
  const project=edit();project.assets=Object.fromEntries(Array.from({length:99},(_,i)=>[i,{}]));
  assert.throws(()=>planMediaImports([audio(),image()],project),/room for 1 more.*nothing was imported/);
  assert.throws(()=>planMediaImports([video()],null),/Open a project/);
  assert.throws(()=>planMediaImports([video()],{...empty(),settings:{workflow:'ai'}}),/manual editor/);
});
test('source import is separate from the 100-asset pool capacity',()=>{
  const project=empty();project.assets=Object.fromEntries(Array.from({length:100},(_,i)=>[i,{}]));
  assert.equal(planMediaImports([video()],project).files.length,1);
  assert.throws(()=>planMediaImports([video(),audio()],project),/room for 0 more/);
});
test('queue is strictly serial through preparation and releases completed file handles',async()=>{
  const first=deferred(),calls=[];
  const queue=new MediaImportQueue({projectId:'one',files:[video(),audio(),image()],currentProjectId:()=> 'one',
    importFile:async file=>{calls.push(file.name);return calls.length===1?first.promise:{status:'ready'};}});
  const operation=queue.run();assert.deepEqual(calls,['video.mp4']);assert.deepEqual(statuses(queue),['importing','queued','queued']);
  await queue.run();assert.deepEqual(calls,['video.mp4'],'a second run must not duplicate active uploads');
  first.resolve({status:'ready'});await operation;
  assert.deepEqual(calls,['video.mp4','sound.wav','title.png']);assert.deepEqual(statuses(queue),['ready','ready','ready']);
  assert.equal(queue.running,false);assert.equal(queue.finished,true);assert.ok(queue.items.every(item=>item.file===null));
});
test('failed file stops later uploads and does not roll back completed files',async()=>{
  const calls=[];const queue=new MediaImportQueue({projectId:'one',files:[video(),audio(),image()],currentProjectId:()=> 'one',
    importFile:async file=>{calls.push(file.name);return calls.length===2?{status:'failed',message:'Unsupported audio codec'}:{status:'ready'};}});
  await queue.run();assert.deepEqual(calls,['video.mp4','sound.wav']);assert.deepEqual(statuses(queue),['ready','failed','not_imported']);
  assert.match(queue.reason,/Unsupported audio codec.*Completed imports are kept/);
});
test('Stop before admission sends nothing and Stop during a file never advances the queue',async()=>{
  let calls=0;const gate=deferred();
  const early=new MediaImportQueue({projectId:'one',files:[video()],currentProjectId:()=> 'one',importFile:async()=>{calls++;}});
  early.stop();await early.run();assert.equal(calls,0);assert.deepEqual(statuses(early),['not_imported']);
  const running=new MediaImportQueue({projectId:'one',files:[video(),audio()],currentProjectId:()=> 'one',importFile:async(file,live)=>{
    calls++;await gate.promise;assert.equal(live(),false);return {status:'ready'};}});
  const operation=running.run();running.stop();gate.resolve();await operation;
  assert.equal(calls,1);assert.deepEqual(statuses(running),['ready','not_imported']);assert.match(running.reason,/Completed imports are kept/);
});
test('project switch cannot send queued files into the new project',async()=>{
  let projectId='one',calls=0;const gate=deferred();
  const queue=new MediaImportQueue({projectId,files:[video(),audio()],currentProjectId:()=>projectId,
    importFile:async()=>{calls++;await gate.promise;return {status:'ready'};}});
  const operation=queue.run();projectId='two';gate.resolve();await operation;
  assert.equal(calls,1);assert.deepEqual(statuses(queue),['ready','not_imported']);assert.match(queue.reason,/original project/);
});
test('late Stop counts the committed current file as ready but starts no further file',async()=>{
  const queue=new MediaImportQueue({projectId:'one',files:[video(),audio()],currentProjectId:()=> 'one',
    importFile:async()=>({status:'ready',stop:true,message:'Finished before Stop. Remaining files were not imported.'})});
  await queue.run();assert.deepEqual(statuses(queue),['ready','not_imported']);assert.match(queue.reason,/Finished before Stop/);
});
test('missing success result and thrown errors are never reported as ready',async()=>{
  for(const importFile of [async()=>undefined,async()=>{throw new Error('Read failed');}]){
    const queue=new MediaImportQueue({projectId:'one',files:[video(),audio()],currentProjectId:()=> 'one',importFile});
    await queue.run();assert.deepEqual(statuses(queue),['failed','not_imported']);
  }
});
test('media UI queue waits for each real upload acceptance and blocks a second selection',async()=>{
  const {studio}=studioHarness(),gate=deferred(),calls=[];
  studio.options.uploadFile=async file=>{calls.push(file.name);return {};};
  studio.options.acceptUpload=async()=>{if(calls.length===1)await gate.promise;};
  const operation=studio.uploadFiles([video(),audio()]);
  for(let i=0;i<8;i++)await Promise.resolve();
  assert.deepEqual(calls,['video.mp4']);assert.equal(await studio.uploadFiles([image()]),null);
  gate.resolve();const queue=await operation;
  assert.deepEqual(calls,['video.mp4','sound.wav']);assert.deepEqual(statuses(queue),['ready','ready']);
});
test('Stop while pending saves prevents even the first asset request',async()=>{
  const {studio}=studioHarness(),gate=deferred();let requests=0,cancels=0;
  studio.flush=()=>gate.promise;studio.options.uploadFile=async()=>{requests++;return {};};
  studio.options.cancelImport=()=>{cancels++;};
  const operation=studio.uploadFiles([video(),audio()]);studio.stopImports();gate.resolve(true);const queue=await operation;
  assert.equal(requests,0);assert.equal(cancels,1);assert.deepEqual(statuses(queue),['cancelled','not_imported']);
});
test('empty mixed batch imports primary once and routes all following files to assets',async()=>{
  const {studio,activate}=studioHarness(empty()),calls=[];
  studio.options.prepareEmptyImport=async file=>{calls.push(['source',file.name]);activate(edit());return true;};
  studio.options.uploadFile=async file=>{calls.push(['asset',file.name]);return {};};
  const queue=await studio.uploadFiles([audio(),video(),image()]);
  assert.deepEqual(calls,[['source','video.mp4'],['asset','sound.wav'],['asset','title.png']]);
  assert.deepEqual(statuses(queue),['ready','ready','ready']);
});

for(const kind of ['video','audio','image'])test(`timeline drop places ${kind} through native media_add at the supplied time`,async()=>{
  const {studio,activate,project}=studioHarness();let call;
  studio.options.edit=async(action,payload)=>{call={action,payload};const updated={...project(),manual:{media_clips:[{id:'new',asset_id:kind}]}};activate(updated);return updated;};
  const result=await studio.place(kind,1.25);
  assert.deepEqual(JSON.parse(JSON.stringify(call)),{action:'media_add',payload:{asset_id:kind,start:1.25}});
  assert.equal(result.id,'one');assert.equal(studio.selected,'new');assert.match(studio.status.textContent,/Undo/);
});
test('end drop appends only video without changing its source or passing an overlay time',async()=>{
  const {studio,activate,project}=studioHarness();let call;
  studio.options.edit=async(action,payload)=>{call={action,payload};const updated={...project(),manual:{media_clips:[{id:'new',asset_id:'video'}]}};activate(updated);return updated;};
  await studio.place('video',8,{append:true});
  assert.deepEqual(JSON.parse(JSON.stringify(call)),{action:'media_append',payload:{asset_id:'video'}});
  call=null;assert.equal(await studio.place('audio',8,{append:true}),null);assert.equal(call,null);
});
test('placement refuses batch/busy/not-ready/invalid-time targets and rechecks after saving',async()=>{
  for(const fault of ['queue','busy','uploading','missing','not-ready','negative','nan','tail','project-switch','removed-during-save']){
    const {studio,activate,project}=studioHarness();let calls=0,time=1;
    studio.options.edit=async()=>{calls++;};
    if(fault==='queue')studio.importQueue={running:true};if(fault==='busy')studio.options.busy=()=>true;
    if(fault==='uploading')studio.uploading=true;if(fault==='missing')delete project().assets.video;
    if(fault==='not-ready')project().assets.video.status='preparing';
    if(fault==='negative')time=-1;if(fault==='nan')time=NaN;if(fault==='tail')time=8;
    studio.flush=async()=>{if(fault==='project-switch')activate({...edit(),id:'two'});if(fault==='removed-during-save')delete project().assets.video;return true;};
    assert.equal(await studio.place('video',time),null,fault);assert.equal(calls,0,fault);
  }
});
test('concurrent drop attempts cannot duplicate a placement while pending saves settle',async()=>{
  const {studio,activate,project}=studioHarness(),gate=deferred();let calls=0;
  studio.flush=()=>gate.promise;studio.options.edit=async()=>{calls++;const updated={...project(),manual:{media_clips:[{id:'new',asset_id:'video'}]}};activate(updated);return updated;};
  const first=studio.place('video',1);assert.equal(await studio.place('video',1),null);gate.resolve(true);await first;
  assert.equal(calls,1);assert.equal(studio.placing,false);
});


test('successful queue receipt collapses once but failures and stopped batches remain open',async()=>{
  for(const outcome of ['ready','failed','cancelled']){
    const {studio}=studioHarness();studio.importQueuePanel={open:false};studio.renderImportQueue=()=>{};
    studio.upload=async()=>({status:outcome,message:'Synthetic result'});
    await studio.uploadFiles([video()]);
    assert.equal(studio.importQueuePanel.open,outcome!=='ready');
    studio.importQueuePanel.open=true;studio.render();assert.equal(studio.importQueuePanel.open,true,'later renders must preserve an explicit reopen');
  }
});
test('import availability unlocks again after unrelated manual-edit busy state clears',()=>{
  const {studio}=studioHarness();studio.importButton={disabled:false};let busy=true;studio.options.busy=()=>busy;
  studio.updateImportAvailability();assert.equal(studio.importButton.disabled,true);
  busy=false;studio.updateImportAvailability();assert.equal(studio.importButton.disabled,false);
  studio.importQueue={running:true};studio.updateImportAvailability();assert.equal(studio.importButton.disabled,true);
});
test('storage details stay collapsed during successful import and expand for a visible storage failure',async()=>{
  for(const fails of [false,true]){
    const {studio}=studioHarness();studio.storageStatus={textContent:'',hidden:true};studio.storageDetails={hidden:true,open:false};
    studio.options.uploadFile=async(file,projectId,report)=>{report('Checking storage','D: local media; 20 GB free; 1 GB required');
      assert.equal(studio.storageDetails.hidden,false);assert.equal(studio.storageDetails.open,false);
      if(fails)throw new Error('Insufficient space for this file');return {};};
    await studio.upload(video());assert.match(studio.storageStatus.textContent,/20 GB free/);assert.equal(studio.storageDetails.open,fails);
  }
});


test('drop selects its last-added occurrence if revision retry also reveals a concurrent copy of the same asset',async()=>{
  const {studio,activate,project}=studioHarness();
  studio.options.edit=async()=>{const updated={...project(),manual:{media_clips:[
    {id:'concurrent-copy',asset_id:'video',start:0},{id:'our-copy',asset_id:'video',start:2}]}};
    activate(updated);return updated;};
  await studio.place('video',2);assert.equal(studio.selected,'our-copy');
});
