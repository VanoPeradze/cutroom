const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const test=require('node:test');
function load(){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+';globalThis.api={MediaStudio,libraryInsertReadiness};',context);return context.api;}
const {MediaStudio,libraryInsertReadiness}=load();
function project(){return {id:'one',revision:4,draft:{output_duration:10,audio_plan:[]},assets:{video:{id:'video',kind:'video',duration:2,status:'ready'},audio:{id:'audio',kind:'audio',duration:10,status:'ready'},image:{id:'image',kind:'image',status:'ready'}},manual:{media_clips:[],text_clips:[]}};}
function crossing(kind,extra={}){return {id:'old',asset_id:kind,start:2,end:6,motion:'none',fade_in:.5,fade_out:.5,...extra};}
function harness(p=project()){const studio=Object.create(MediaStudio.prototype);let current=p;Object.assign(studio,{options:{project:()=>current,busy:()=>false,pause(){},flushSettings:async()=>{},edit:async()=>null},status:{textContent:''},flush:async()=>true,render(){},selected:'old-selection'});return {studio,p:()=>current,activate:p=>current=p};}

test('all static media kinds and custom titles/captions can cross a genuine middle insert',()=>{
 const p=project();p.manual.media_clips=['video','audio','image'].map(kind=>crossing(kind));p.manual.text_clips=[{start:1,end:7,kind:'title'},{start:2,end:6,kind:'caption'}];
 assert.equal(libraryInsertReadiness(p,3,2),'');assert.equal(harness(p).studio.insertionIssue('video',3),'');
});
for(const [patch,reason] of [[{motion:'pan'},/animated/],[{motion:'zoom_in'},/animated/],[{fade_in:1.1},/fade/],[{fade_out:3.1},/fade/],[{start:2.921},/shorter/],[{end:3.079},/shorter/]])test(`insert readiness blocks unrepresentable crossing ${JSON.stringify(patch)}`,()=>{
 const p=project();p.manual.media_clips=[crossing('video',patch)];assert.match(libraryInsertReadiness(p,3,2),reason);
});
test('fade boundaries and minimum .08-second pieces are accepted without inventing new fades',()=>{
 const p=project();p.manual.media_clips=[crossing('video',{start:2.92,end:3.08,fade_in:.08,fade_out:.08})];p.manual.text_clips=[{start:2.92,end:3.08}];assert.equal(libraryInsertReadiness(p,3,2),'');
});
test('motion or fades on wholly downstream/upstream clips do not disable insert',()=>{
 const p=project();p.manual.media_clips=[crossing('video',{start:0,end:2,motion:'pan'}),crossing('video',{start:3,end:6,motion:'zoom_in'})];assert.equal(libraryInsertReadiness(p,3,2),'');
});
test('ready ownership and explicit automatic-caption boundaries stay protected',()=>{
 const p=project();p.manual.caption_overrides={edited:{text:'Mine'}};p.editor_captions=[{id:'edited',start:2,end:4}];assert.match(libraryInsertReadiness(p,3),/edited caption/);
 assert.equal(libraryInsertReadiness(p,4),'');delete p.editor_captions;assert.match(libraryInsertReadiness(p,4),/owner/);
 delete p.manual.caption_overrides;p.manual.caption_dormant_overrides={uncertain:{}};assert.match(libraryInsertReadiness(p,3),/uncertain/);
 delete p.manual.caption_dormant_overrides;p.manual.media_clips=[crossing('video')];p.assets.video.status='failed';assert.match(libraryInsertReadiness(p,3),/not ready/);
});
test('existing timed plans, active alternatives and affected source locks are gated but end append stays available',()=>{
 const p=project();p.draft.audio_plan=[{}];assert.match(libraryInsertReadiness(p,3),/audio plan/);assert.equal(libraryInsertReadiness(p,10),'');p.draft.audio_plan=[];
 p.caption_alternative_status={active_id:'saved'};assert.match(libraryInsertReadiness(p,3),/alternative/);delete p.caption_alternative_status;
 p.manual.track_locks={A:true};p.editor_sequence={duration:10,source_tracks:{A:[{start:0,end:7}]}};assert.match(libraryInsertReadiness(p,3),/locked/);assert.equal(libraryInsertReadiness(p,8),'');
});
test('all newly split pieces and new shot count toward bounded capacity and full duration',()=>{
 const p=project();p.manual.media_clips=Array.from({length:199},()=>crossing('video'));assert.match(libraryInsertReadiness(p,3),/200 media/);
 p.manual.media_clips=[];p.manual.text_clips=Array.from({length:2000},()=>({start:2,end:6}));assert.match(libraryInsertReadiness(p,3),/2000 text/);
 p.manual.text_clips=[];p.draft.output_duration=86399;assert.match(libraryInsertReadiness(p,3,2),/24 hours/);
});
test('insert placement emits one native media_insert, returns/selects its final occurrence and pins revision',async()=>{
 const h=harness();let call,guard;
 h.studio.options.edit=async(action,payload,options)=>{call={action,payload};guard=options.isCurrent;assert.equal(guard(),true);const result={...h.p(),revision:5,manual:{media_clips:[{id:'split-right',asset_id:'video'},{id:'new-shot',asset_id:'video'}]}};h.activate(result);return result;};
 const result=await h.studio.place('video',3,{insert:true});assert.deepEqual(JSON.parse(JSON.stringify(call)),{action:'media_insert',payload:{asset_id:'video',start:3}});assert.equal(result.revision,5);assert.equal(h.studio.selected,'new-shot');assert.equal(guard(),false);assert.match(h.studio.status.textContent,/inserted.*Undo/);assert.equal(h.studio.placing,false);
});
test('insert refuses invalid mode, nonvideo, active import, unsafe crossings and timeline changes during saves',async()=>{
 for(const fault of ['audio','image','both','flag','queue','motion','fade','save-failed','revision','project','settings-revision']){
  const h=harness();let calls=0;h.studio.options.edit=async()=>{calls++;};let asset='video',options={insert:true};
  if(['audio','image'].includes(fault))asset=fault;if(fault==='both')options.append=true;if(fault==='flag')options.insert='yes';
  if(fault==='queue')h.studio.importQueue={running:true};if(fault==='motion')h.p().manual.media_clips=[crossing('video',{motion:'pan'})];if(fault==='fade')h.p().manual.media_clips=[crossing('audio',{fade_in:2})];
  h.studio.flush=async()=>{if(fault==='revision')h.p().revision++;if(fault==='project')h.activate({...h.p(),id:'two'});return fault!=='save-failed';};h.studio.options.flushSettings=async()=>{if(fault==='settings-revision')h.p().revision++;};
  assert.equal(await h.studio.place(asset,3,options),null,fault);assert.equal(calls,0,fault);assert.equal(h.studio.selected,'old-selection',fault);
 }
});
test('late rejected insertion never claims success and guards against applying after a refreshed revision',async()=>{
 const h=harness();h.studio.options.edit=async(_action,_payload,{isCurrent})=>{h.activate({...h.p(),revision:9});assert.equal(isCurrent(),false);return null;};
 assert.equal(await h.studio.place('video',3,{insert:true}),null);assert.match(h.studio.status.textContent,/nothing was inserted/);assert.equal(h.studio.selected,'old-selection');
});


test('idle readiness restores existing media-card actions after save/Undo without repainting the pool or receipt',()=>{
 const h=harness(),p=h.p();p.assets.failed={id:'failed',status:'failed',kind:'video'};
 const buttons=[{dataset:{asset:'video'}},{dataset:{append:'video'}},{dataset:{reviewShot:'video'}},{dataset:{asset:'audio'}},{dataset:{retry:'failed'}}];
 let busy=true;h.studio.options.busy=()=>busy;h.studio.importButton={disabled:false};
 const receipt={open:true,textContent:'Complete queue'};h.studio.importQueuePanel=receipt;
 h.studio.library={scrollTop:144,querySelectorAll:()=>buttons,replaceChildren(){throw Error('readiness must not rebuild media cards');}};
 h.studio.updateImportAvailability();assert.ok(buttons.every(button=>button.disabled));assert.equal(h.studio.importButton.disabled,true);
 busy=false;h.studio.updateImportAvailability();assert.ok(buttons.every(button=>!button.disabled));assert.equal(h.studio.importButton.disabled,false);
 assert.equal(h.studio.library.scrollTop,144);assert.equal(h.studio.importQueuePanel,receipt);assert.equal(receipt.open,true);
 for(const operation of ['queue','uploading']){if(operation==='queue')h.studio.importQueue={running:true};else h.studio.uploading=true;
  h.studio.updateImportAvailability();assert.ok(buttons.every(button=>button.disabled));h.studio.importQueue=null;h.studio.uploading=false;}
});
test('lightweight card refresh never unlocks missing, preparing, nonvideo review or unavailable timeline actions',()=>{
 const h=harness(),p=h.p();p.assets.video.status='preparing';p.assets.failed={id:'failed',status:'ready',kind:'video'};
 const buttons=[{dataset:{asset:'video'}},{dataset:{append:'audio'}},{dataset:{reviewShot:'image'}},{dataset:{retry:'failed'}},{dataset:{asset:'missing'}}];
 h.studio.library={querySelectorAll:()=>buttons};h.studio.updateImportAvailability();assert.ok(buttons.every(button=>button.disabled));
 p.assets.video.status='ready';p.assets.failed.status='cancelled';p.draft=null;h.studio.updateImportAvailability();assert.equal(buttons[0].disabled,true);assert.equal(buttons[3].disabled,false,'retry does not require an existing timeline');
});

for(const reserved of [0,1])for(const enabled of [true,false])test('Source and media Insert block a crossing Chapter before commit: '+reserved+'/'+enabled,()=>{
 const p=project();p.manual.media_clips=[];p.manual.text_clips=[{id:'t',start:3,end:5,kind:'title',template:'chapter',enabled}];
 const before=JSON.stringify(p);assert.match(libraryInsertReadiness(p,4,.5,reserved),/Chapter.*fade/i);
 for(const at of [2,3,5,6])assert.equal(libraryInsertReadiness(p,at,.5,reserved),'');
 for(const template of ['plain','lower_third','callout','highlight']){const stable=JSON.parse(before);stable.manual.text_clips[0].template=template;assert.equal(libraryInsertReadiness(stable,4,.5,reserved),'');}
 assert.equal(JSON.stringify(p),before);
});
