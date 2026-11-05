const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const start = source.indexOf('function podcastFramingCues(project)');
const end = source.indexOf('function renderPodcastFraming()',start);
function setup(rows, revision=1) {
 const nodes = new Map();
 const node = () => ({children:[],dataset:{},listeners:{},replaceChildren(){this.children=[];},append(n){this.children.push(n);},addEventListener(k,fn){this.listeners[k]=fn;}});
 nodes.set('podcastFramingCues',node());nodes.set('podcastFramingCuesHelp',node());
 const project={id:'p',revision,editor_sequence:{},sources:{A:{generation:'source1'}},rows};
 const ctx=vm.createContext({Number,Math,state:{project},trackClips:p=>p.rows,document:{getElementById:id=>nodes.get(id),createElement:node},uiCopy:(_he,en)=>en,editorProject:()=>project,foregroundBusy:()=>false,formatSourceTime:x=>x.toFixed(3),setManualSelection:s=>ctx.selection=s,seekPreview:t=>ctx.seek=t,syncSecondaryPreview:()=>{},previewPlaybackTime:()=>0,toast:s=>ctx.notice=s});
 vm.runInContext(source.slice(start,end),ctx);
 return {ctx,nodes,project,run:code=>vm.runInContext(code,ctx)};
}
const crop={x:.5,y:0,zoom:2};
const clip=(start,end,c=crop)=>({start,end,source_start:start,crop:c});
const plain=x=>JSON.parse(JSON.stringify(x));
test('ordered saved ranges retain exact timing and crop without mutation',()=>{
 const rows=[clip(0,2),clip(2,4),clip(5,7,{x:.5,y:1,zoom:2.1})];const before=JSON.stringify(rows);const h=setup(rows);
 assert.deepEqual(plain(h.run('podcastFramingCues(state.project)')).map(r=>[r.start,r.end,r.crop.y]),[[0,4,0],[5,7,1]]);assert.equal(JSON.stringify(rows),before);
});
test('gaps and different framing stay separate',()=>{
 const h=setup([clip(0,1),clip(2,3),clip(3,4,{...crop,zoom:2.1})]);assert.equal(h.run('podcastFramingCues(state.project).length'),3);
});
test('Both and invalid rows are not misleading cues',()=>{
 const h=setup([clip(0,1,{x:.5,y:.5,zoom:1}),clip(1,2,{...crop,zoom:NaN}),clip(2,2)]);assert.equal(h.run('podcastFramingCues(state.project).length'),0);
});
test('legacy project without sequence has no editable cue list',()=>{
 const h=setup([clip(0,2)]);h.project.editor_sequence=null;assert.equal(h.run('podcastFramingCues(state.project).length'),0);
});
test('selecting saved cue uses current timeline and seeks inside it',()=>{
 const h=setup([clip(1.234,5.678)]);h.run('renderPodcastFramingCues()');const button=h.nodes.get('podcastFramingCues').children[0];assert.match(button.textContent,/1.234–5.678/);button.listeners.click();assert.deepEqual(plain(h.ctx.selection),{start:1.234,end:5.678});assert.ok(Math.abs(h.ctx.seek-1.274)<1e-9);
});
for(const field of ['revision','source','project'])test('stale '+field+' cue cannot select outdated range',()=>{
 const h=setup([clip(0,2)]);h.run('renderPodcastFramingCues()');const button=h.nodes.get('podcastFramingCues').children[0];if(field==='revision')h.project.revision++;if(field==='source')h.project.sources.A.generation='source2';if(field==='project')h.project.id='other';button.listeners.click();assert.equal(h.ctx.selection,undefined);assert.match(h.ctx.notice,/changed/);
});
test('Undo/current crops rebuild the cue view without separate persisted state',()=>{
 const h=setup([clip(0,2)]);h.run('renderPodcastFramingCues()');assert.equal(h.nodes.get('podcastFramingCues').children.length,1);h.project.rows=[clip(0,2,{x:.5,y:.5,zoom:1})];h.run('renderPodcastFramingCues()');assert.equal(h.nodes.get('podcastFramingCues').hidden,true);h.project.rows=[clip(0,2)];h.run('renderPodcastFramingCues()');assert.equal(h.nodes.get('podcastFramingCues').children.length,1);
});
test('in-flight edit disables navigation to stale cue state',()=>{
 const h=setup([clip(0,2)]);h.ctx.state.manualEditBusy=true;h.run('renderPodcastFramingCues()');assert.equal(h.nodes.get('podcastFramingCues').children[0].disabled,true);
});

test('same crop across a source cut stays two separate selectable cues',()=>{
 const h=setup([clip(0,2),{...clip(2,4),source_start:20}]);assert.equal(h.run('podcastFramingCues(state.project).length'),2);
});
test('sorted cue display never reorders underlying source clips',()=>{
 const rows=[clip(3,5),clip(0,2)];const h=setup(rows);assert.equal(h.run('podcastFramingCues(state.project)[0].start'),0);assert.equal(rows[0].start,3);
});
test('click racing an edit is ignored even if button was drawn enabled',()=>{
 const h=setup([clip(0,2)]);h.run('renderPodcastFramingCues()');const b=h.nodes.get('podcastFramingCues').children[0];h.ctx.state.manualEditBusy=true;b.listeners.click();assert.equal(h.ctx.selection,undefined);
});
