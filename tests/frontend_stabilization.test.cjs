const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/stabilization-studio.js', 'utf8').replace('export class StabilizationStudio', 'class StabilizationStudio');
const context = vm.createContext({console, JSON, encodeURIComponent});
vm.runInContext(source + '\nthis.StabilizationStudio = StabilizationStudio;', context);

function fixture() {
  const project = {id:'project_fixture', revision:7, sources:{A:{name:'Original.mp4', preparation:'ready'}}, assets:{}, manual:{keeps:[1,2]}};
  let current = project;
  const calls = [];
  const studio = Object.create(context.StabilizationStudio.prototype);
  Object.assign(studio, {
    uploading:false, starting:false, capability:{available:true}, source:{value:'A'}, status:{textContent:''},
    download:{hidden:true}, render(){}, options:{
      project:()=>current, busy:()=>false, pause(){}, flush:async()=>true, flushSettings:async()=>{}, busyChanged(){},
      api:async(url, request)=>{calls.push([url, JSON.parse(request.body)]); return {asset_id:'asset_copy', job:{id:'job_copy'}};},
      acceptUpload:async()=>{current.assets.asset_copy={status:'ready', name:'Original-stabilized.mp4', download_url:'/api/projects/project_fixture/assets/asset_copy/download'};},
    },
  });
  return {studio, project, calls, switchProject:p=>{current=p;}};
}

test('stabilization makes one explicit copy request and offers the full download without changing sources or edits', async()=>{
  const {studio,project,calls}=fixture();
  const originals=JSON.stringify({sources:project.sources,manual:project.manual});
  await studio.createCopy();
  assert.deepEqual(calls,[['/api/projects/project_fixture/stabilize',{slot:'A',expected_revision:7}]]);
  assert.equal(JSON.stringify({sources:project.sources,manual:project.manual}),originals);
  assert.equal(studio.download.hidden,false);
  assert.equal(studio.download.href,project.assets.asset_copy.download_url);
  assert.equal(studio.downloadProjectId,project.id);
  assert.equal(studio.uploading,false);
  assert.equal(studio.starting,false);
  assert.match(studio.status.textContent,/original edit is unchanged/);
});

test('failed or cancelled processing never exposes an unfinished copy and clears the busy state', async()=>{
  for(const message of ['Job cancelled','This source changed; create a new copy.']){
    const {studio}=fixture();
    studio.options.acceptUpload=async()=>{throw new Error(message);};
    await studio.createCopy();
    assert.equal(studio.download.hidden,true);
    assert.equal(studio.status.textContent,message);
    assert.equal(studio.starting,false);
    assert.equal(studio.uploading,false);
  }
});

test('missing capability or project processing prevents a new copy request', async()=>{
  const {studio,calls}=fixture();
  studio.capability={available:false};
  await studio.createCopy();
  studio.capability={available:true};
  studio.options.busy=()=>true;
  await studio.createCopy();
  assert.equal(calls.length,0);
});

test('a double click while pending settings are flushed starts only one job',async()=>{
  const {studio,calls}=fixture();
  let release;
  studio.options.flush=()=>new Promise(resolve=>{release=resolve;});
  const first=studio.createCopy();
  await studio.createCopy();
  release(true);
  await first;
  assert.equal(calls.length,1);
});

test('switching project during processing does not show the old copy in the new project',async()=>{
  const {studio,switchProject}=fixture();
  studio.options.acceptUpload=async()=>{switchProject({id:'project_other',revision:1,sources:{},assets:{}});};
  await studio.createCopy();
  assert.equal(studio.download.hidden,true);
  assert.equal(studio.downloadProjectId,undefined);
  assert.equal(studio.uploading,false);
});
