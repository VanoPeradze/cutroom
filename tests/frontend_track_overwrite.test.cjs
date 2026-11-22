const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=f=>fs.readFileSync(path.join(__dirname,'../web',f),'utf8').replace(/^import .*;\r?$/gm,'').replace(/^export /gm,'');
const {layerTrackState}=vm.runInNewContext(src('layer-tracks.js')+'\n;({layerTrackState})');
const {planTrackOverwrite,describeTrackOverwrite,verifyTrackOverwrite}=vm.runInNewContext(src('track-overwrite.js')+'\n;({planTrackOverwrite,describeTrackOverwrite,verifyTrackOverwrite})',{layerTrackState});
const plain=x=>JSON.parse(JSON.stringify(x)), id=(a,k)=>a+'_'+k.repeat(32),a=k=>id('asset',k),c=k=>id('media',k),t=k=>id('track',k),T=t('d'),U=t('e'),A=a('8');
function data(fps=30,mode='cross'){
 const assets={};for(const [k,kind] of [['1','video'],['2','video'],['4','video'],['8','video'],['7','audio']])assets[a(k)]={id:a(k),name:k,kind,status:'ready',duration:15,has_audio:true};
 const row=(z,lo,hi,x={})=>({id:c(z),asset_id:a(z),track_id:T,start:lo,end:hi,source_start:.5,video_source_start:1.13,speed:1.5,fade_in:0,fade_out:0,motion:'none',volume_db:-3,muted:false,role:'voice',audio_enabled:true,x:0,y:0,w:1,h:1,fit:'cover', ...x});
 const left=row('1',3,5,{fade_in:.12}),mid=row('4',5,6.5,{motion:'pan',fade_in:.23,fade_out:.13}),right=row('2',6.5,8.5,{speed:.5,enabled:false,fade_out:.14}),other=row('7',4,8,{track_id:U,speed:1});
 const tracks=[{id:T,kind:'visual',name:'Story',locked:false},{id:U,kind:'audio',name:'Score',locked:true}];if(mode==='empty')tracks.push({id:t('8'),kind:'visual',name:'B-roll',locked:false});
 const clips=mode==='split'?[other,{...left,start:3.01234567891,end:8.43}]:[right,mid,other,left];
 return {id:'project_test',revision:5,assets,settings:{fps},draft:{output_duration:14},editor_sequence:{duration:14},editor_captions:[{id:'a'}],manual:{media_clips:clips,history:{undo_count:2,redo_count:1},text_clips:[],layer_tracks:{version:2,tracks},audio_mixer:{master_db:-1}}};
}
const d=(fps=30,mode='cross')=>({asset_id:A,track_id:mode==='empty'?t('8'):T,frame:Math.round(4.5*fps),source_start:.63,source_end:3.38});
function saved(p,d){const q=planTrackOverwrite(p,d),r=structuredClone(p);assert.equal(q.issue,'');let i=0;r.manual.media_clips=plain(q.rows).map(x=>({...x,id:x.id??c(['9','b','a'][i++])}));r.revision++;r.manual.history={undo_count:3,redo_count:0};return r;}
for(const fps of [24,25,30,50,60])for(const mode of ['cross','split','empty'])test('exact non-ripple overwrite '+mode+' at '+fps,()=>{const p=data(fps,mode),raw=structuredClone(p),detail=d(fps,mode);const q=planTrackOverwrite(p,detail);assert.equal(q.issue,'');
 assert.deepEqual(plain(q.counts),mode==='cross'?{removed:1,trimmed:2,split:0}:mode==='split'?{removed:0,trimmed:0,split:1}:{removed:0,trimmed:0,split:0});
 const r=saved(p,detail);assert.equal(verifyTrackOverwrite(p,r,detail),'');assert.deepEqual(r.manual.media_clips.filter(x=>x.track_id!==detail.track_id),p.manual.media_clips.filter(x=>x.track_id!==detail.track_id));assert.deepEqual(p,raw);assert.match(describeTrackOverwrite(q),/other tracks and edit length stay fixed/);});
for(const [w,modify,re] of [
 ['automatic',(p,d)=>d.track_id='',/named/],['audio target',(p,d)=>d.track_id=U,/named/],['locked',(p,d)=>p.manual.layer_tracks.tracks[0].locked=true,/Unlock/],['untracked',(p,d)=>{delete p.manual.layer_tracks;for(const r of p.manual.media_clips)delete r.track_id;},/Enable/],
 ['unsupported model',(p,d)=>p.manual.layer_tracks.version=4,/version|track/i],['bad fps',(p,d)=>p.settings.fps=29.97,/frame/],['no frame',(p,d)=>delete d.frame,/frame/],['fraction',(p,d)=>d.frame+=.5,/frame/],['bool',(p,d)=>d.frame=true,/frame/],['over end',(p,d)=>d.frame=405,/edit end/],
 ['wrong asset',(p,d)=>d.asset_id=a('7'),/video/],['unknown',(p,d)=>d.asset_id=a('a'),/video/],['source not ready',(p,d)=>p.assets[A].status='busy',/ready/],['source short',(p,d)=>p.assets[A].duration=2,/inside/],['no In',(p,d)=>delete d.source_start,/inside/],['negative In',(p,d)=>d.source_start=-1e-10,/inside/],
 ['string',(p,d)=>d.source_end='4',/inside/],['nonfinite',(p,d)=>d.source_end=NaN,/inside/],['reversed',(p,d)=>d.source_end=.4,/0.08/],['range short',(p,d)=>d.source_end=.64,/0.08/],
 ['partial pan',(p,d)=>p.manual.media_clips[3].motion='pan',/pan/],['other partial pan',(p,d)=>p.manual.media_clips[0].motion='zoom_in',/pan/],
 ['left inside fade-in',(p,d)=>p.manual.media_clips[3].fade_in=1.8,/fade/],['left inside fade-out',(p,d)=>p.manual.media_clips[3].fade_out=.8,/fade/],
 ['right inside fade-in',(p,d)=>p.manual.media_clips[0].fade_in=1,/fade/],['right inside fade-out',(p,d)=>p.manual.media_clips[0].fade_out=1.4,/fade/],
 ['tiny left',(p,d)=>{p.manual.media_clips[3].start=4.46;p.manual.media_clips[3].fade_in=0;},/0.08/],['tiny right',(p,d)=>{p.manual.media_clips[0].end=7.29;p.manual.media_clips[0].fade_out=0;},/0.08/],
 ['missing original',(p,d)=>p.assets[a('1')].status='failed',/original/],['invalid retained clock',(p,d)=>p.manual.media_clips[0].video_source_start=-1,/timing/]
])test('refuse '+w+' without editing any object',()=>{const p=data(),dt=d();modify(p,dt);const b=structuredClone(p);assert.match(planTrackOverwrite(p,dt).issue,re);assert.deepEqual(p,b);});
for(const [w,damage] of [['reused placed ID',r=>r.manual.media_clips.at(-1).id=c('1')],['wrong split ID',r=>r.manual.media_clips[2].id=c('7')],
 ['other track',r=>r.manual.media_clips[0].volume_db=-25],['left timeline',r=>r.manual.media_clips[1].end+=.001],['right picture',r=>r.manual.media_clips[2].video_source_start+=.02],['right sound',r=>r.manual.media_clips[2].source_start+=.02],
 ['right motion',r=>r.manual.media_clips[2].motion='pan'],['new start',r=>r.manual.media_clips.at(-1).start+=.01],['new attached sound',r=>r.manual.media_clips.at(-1).audio_enabled=false],['order',r=>r.manual.media_clips.reverse()],
 ['source ref',r=>r.assets[A].duration++],['caption',r=>r.editor_captions=[]],['settings',r=>r.settings.fps=50],['track mix',r=>r.manual.audio_mixer.master_db=4],['undo',r=>r.manual.history.undo_count++],['revision',r=>r.revision++],['view',r=>r.id='wrong']])test('reject incorrect saved '+w,()=>{const p=data(30,'split'),finish=saved(p,d());damage(finish);assert.notEqual(verifyTrackOverwrite(p,finish,d()),'');});
test('disabled full coverage counts, locked other tracks and material exactly touching an edge survive',()=>{let p=data(),q=d();q.frame=150;q.source_end=q.source_start+1.5;p.manual.media_clips[1].enabled=false;const a=planTrackOverwrite(p,q);assert.deepEqual(plain(a.counts),{removed:1,trimmed:0,split:0});assert.equal(a.rows[0],p.manual.media_clips[0]);assert.equal(a.rows[1],p.manual.media_clips[2]);assert.equal(a.rows[2],p.manual.media_clips[3]);});
