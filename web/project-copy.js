const KEY = 'cutroom-project-copy-operations-v1';
const TOKEN = /^[A-Za-z0-9_-]{16,96}$/;
const PROJECT = /^project_[0-9a-f]{12}$/;
const TERMINAL = new Set(['completed','failed','cancelled','interrupted']);
const SERVER = new Set(['queued','running','publishing',...TERMINAL]);
const fields = ['operation_token','source_project_id','source_revision','name','status','progress','copied_bytes','total_bytes','job_id','copy_project_id','error','cancel_requested'];
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const integer = value => Number.isSafeInteger(value) && value >= 0;
function bindingValid(b) {
  return object(b) && typeof b.operation_token === 'string' && TOKEN.test(b.operation_token)
    && typeof b.source_project_id === 'string' && PROJECT.test(b.source_project_id)
    && integer(b.source_revision) && b.source_revision >= 1 && typeof b.name === 'string'
    && b.name === b.name.trim() && [...b.name].length >= 1 && [...b.name].length <= 120;
}
const binding = b => ({operation_token:b.operation_token,source_project_id:b.source_project_id,source_revision:b.source_revision,name:b.name});
const sameBinding = (a,b) => ['operation_token','source_project_id','source_revision','name'].every(key=>a[key]===b[key]);
function operationValid(op) {
  return bindingValid(op) && fields.every(key=>Object.hasOwn(op,key)) && SERVER.has(op.status)
    && typeof op.progress === 'number' && Number.isFinite(op.progress) && op.progress >= 0 && op.progress <= 1
    && integer(op.copied_bytes) && integer(op.total_bytes) && op.copied_bytes <= op.total_bytes
    && (op.job_id === null || typeof op.job_id === 'string' && /^job_[0-9a-f]{12}$/.test(op.job_id))
    && (op.error === null || typeof op.error === 'string') && typeof op.cancel_requested === 'boolean'
    && (op.status === 'completed' ? typeof op.copy_project_id === 'string' && PROJECT.test(op.copy_project_id)
      && op.copy_project_id !== op.source_project_id && op.progress === 1 && op.copied_bytes === op.total_bytes : op.copy_project_id === null);
}

// Transport/state only. No project data, media, DOM or navigation is copied here.
export function initProjectCopyController({api,prepare,changed,completed,storage=localStorage,
  token=()=>crypto.randomUUID(),schedule=setTimeout,clearSchedule=clearTimeout}) {
  const entries=new Map();let destroyed=false,storageIssue='',readIssue='',discoveryIssue='',recovery=null;
  const busy=e=>!TERMINAL.has(e.op.status);
  function snapshot(e) { if(!e)return null;return Object.freeze({...e.op,known:e.known,pending:e.pending,
    canCancel:!e.pending && (e.op.status==='preparing' || e.known && busy(e) && !e.op.cancel_requested),
    canRetry:!e.pending && e.op.status==='unknown' && !e.known && e.submitted && !storageIssue}); }
  const emit=e=>{if(!destroyed)try{changed?.(snapshot(e));}catch{/* Consumer failure cannot replay an operation. */}};
  const stop=e=>{if(e.timer!==null){clearSchedule(e.timer);e.timer=null;}};
  function poll(e) {stop(e);if(destroyed||!busy(e)||!e.submitted||e.pending)return;
    e.timer=schedule(()=>{e.timer=null;if(!destroyed)void check(e.op.operation_token);},e.known?1000:2500);}
  function persist() {
    if(readIssue)throw Error(readIssue);
    readStored();if(readIssue)throw Error(readIssue);
    const operations=[...entries.values()].filter(e=>e.submitted&&busy(e)).map(e=>binding(e.op));
    try{storage.setItem(KEY,JSON.stringify({version:1,operations}));storageIssue='';}
    catch{storageIssue='Copy recovery could not be saved in this browser. Free browser storage before starting or retrying a copy.';throw Error(storageIssue);}
  }
  function entry(op,known=false,submitted=false) {return {op:{...op},known,submitted,pending:false,cancelled:false,timer:null,flight:null,completion:false,serverPhase:known?op.status:null};}
  function local(b,status,error=null) {return {...b,status,progress:0,copied_bytes:0,total_bytes:0,job_id:null,copy_project_id:null,error,cancel_requested:false};}
  // Merge other tabs' unresolved bindings; never overwrite their recovery evidence.
  function readStored() {
    try {
      const raw=storage.getItem(KEY);if(raw===null)return;
      const saved=JSON.parse(raw);if(!object(saved)||saved.version!==1||!Array.isArray(saved.operations)||saved.operations.length>1000)throw Error();
      const seen=new Set();for(const b of saved.operations){if(!bindingValid(b)||seen.has(b.operation_token))throw Error();seen.add(b.operation_token);
        const old=entries.get(b.operation_token);if(old&&(!old.submitted||!sameBinding(old.op,b)))throw Error();
        if(!old)entries.set(b.operation_token,entry(local(binding(b),'unknown','Checking the saved copy request is required.'),false,true));}
    }catch{readIssue=storageIssue='Saved copy recovery information is unavailable or invalid. Restore browser storage before starting another copy.';}
  }
  readStored();
  function adopt(op) {
    if(destroyed||!operationValid(op))return null;
    let e=entries.get(op.operation_token);
    if(e && !sameBinding(e.op,op))return null;
    if(e && TERMINAL.has(e.op.status))return snapshot(e);
    const rank={queued:0,running:1,publishing:2};
    if(e?.known && rank[op.status]!==undefined && rank[e.serverPhase]>rank[op.status])return snapshot(e);
    if(!e){e=entry(Object.fromEntries(fields.map(k=>[k,op[k]])),true,true);entries.set(op.operation_token,e);}
    else {e.op=Object.fromEntries(fields.map(k=>[k,op[k]]));e.known=true;e.submitted=true;e.serverPhase=op.status;}
    stop(e);try{persist();}catch{/* Known server receipt remains authoritative; new submissions stay fenced. */}
    emit(e);
    if(op.status==='completed'&&!e.completion){e.completion=true;try{completed?.(snapshot(e));}catch{}}
    poll(e);return snapshot(e);
  }
  const receipt=(e,op)=>operationValid(op)&&sameBinding(e.op,op)?adopt(op):null;
  function unknown(e,error) {if(destroyed||TERMINAL.has(e.op.status))return;
    e.op={...e.op,status:'unknown',error:error||'Copy outcome is not yet confirmed. Check status before retrying.'};
    emit(e);}
  async function lookup(e) {
    try{const payload=await api(`/api/project-copies/${encodeURIComponent(e.op.operation_token)}`);
      if(destroyed)return {found:false};const accepted=receipt(e,payload?.operation);if(!accepted){unknown(e,'Copy status returned an invalid or mismatched receipt.');return {found:false};}return {found:true};
    }catch(error){if(!destroyed)unknown(e,error?.status===404?'The server has not confirmed this copy request. Its outcome is still unknown.':'Copy status could not be confirmed. Check again before retrying.');return {found:false,missing:Number(error?.status)===404};}
  }
  function check(id) {
    const e=entries.get(id);if(!e||destroyed)return Promise.resolve(snapshot(e));if(e.flight)return e.flight;if(e.pending)return Promise.resolve(snapshot(e));
    if(TERMINAL.has(e.op.status)||!e.submitted)return Promise.resolve(snapshot(e));
    e.pending=true;stop(e);emit(e);
    const work=(async()=>{await lookup(e);return snapshot(e);})();e.flight=work;
    return work.finally(()=>{if(e.flight===work){e.flight=null;e.pending=false;emit(e);poll(e);}}).then(()=>snapshot(e));
  }
  async function submit(e) {
    if(destroyed||TERMINAL.has(e.op.status))return snapshot(e);
    e.pending=true;stop(e);e.op={...e.op,status:'submitting'};emit(e);
    try {
      const payload=await api(`/api/projects/${encodeURIComponent(e.op.source_project_id)}/copies`,{method:'POST',body:JSON.stringify({expected_revision:e.op.source_revision,name:e.op.name,operation_token:e.op.operation_token})});
      if(!destroyed&&!receipt(e,payload?.operation)){unknown(e,'The copy response could not be verified. Check status before retrying.');await lookup(e);}
    }catch(error){if(!destroyed){unknown(e);const result=await lookup(e);
      if(!result.found&&result.missing&&[400,404,405,409].includes(Number(error?.status))&&!e.known&&!TERMINAL.has(e.op.status)){
        e.op={...e.op,status:'failed',error:error?.message||'The server refused this copy request.'};try{persist();}catch{};emit(e);
      }}}
    finally{e.pending=false;emit(e);poll(e);}return snapshot(e);
  }
  async function start(sourceId,name) {
    if(destroyed)throw Error('Copy controller is closed.');
    readStored();
    const active=[...entries.values()].filter(busy),existing=active.find(e=>e.op.source_project_id===sourceId);
    if(existing)return snapshot(existing);if(active.length)throw Error('Finish or resolve the active project copy first.');
    if(storageIssue){if(readIssue)throw Error(readIssue);persist();}
    if(typeof sourceId!=='string'||!PROJECT.test(sourceId)||typeof name!=='string'||!name.trim()||[...name.trim()].length>120)throw Error('Choose a valid source project and copy name (1–120 characters).');
    const id=token();if(typeof id!=='string'||!TOKEN.test(id)||entries.has(id))throw Error('A unique valid copy request token is required.');
    const e=entry(local({operation_token:id,source_project_id:sourceId,source_revision:null,name:name.trim()},'preparing'));
    entries.set(id,e);emit(e);
    try {
      if(discoveryIssue||recovery){await recover();if(discoveryIssue)throw Error(discoveryIssue);}
      if(destroyed||e.cancelled)return snapshot(e);
      if([...entries.values()].some(other=>other!==e&&busy(other)))throw Error('Resolve the active project copy before preparing another copy.');
      const saved=await prepare(sourceId,{cancelled:()=>destroyed||e.cancelled});
      if(destroyed||e.cancelled)return snapshot(e);
      if(!integer(saved?.revision)||saved.revision<1)throw Error('The saved source revision could not be confirmed.');
      readStored();if(readIssue)throw Error(readIssue);
      if([...entries.values()].some(other=>other!==e&&busy(other)))throw Error('Another copy request appeared while preparing. Resolve it before starting another copy.');
      e.op.source_revision=saved.revision;e.submitted=true;
      try{persist();}catch(error){e.submitted=false;throw error;}
      return await submit(e);
    }catch(error){if(!destroyed&&!e.cancelled&&!e.submitted){e.op={...e.op,status:'failed',error:error?.message||'The source could not be prepared.'};emit(e);}return snapshot(e);}
  }
  function retry(id) {
    const e=entries.get(id);if(!e||destroyed)return Promise.resolve(snapshot(e));if(e.flight)return e.flight;
    if(!snapshot(e).canRetry)return Promise.resolve(snapshot(e));
    try{persist();}catch(error){unknown(e,error.message);return Promise.resolve(snapshot(e));}
    const work=submit(e);e.flight=work;return work.finally(()=>{if(e.flight===work)e.flight=null;}).then(()=>snapshot(e));
  }
  function cancel(id) {
    const e=entries.get(id);if(!e||destroyed)return Promise.resolve(snapshot(e));
    if(e.op.status==='preparing'){e.cancelled=true;e.op={...e.op,status:'cancelled',error:'Cancelled before copy admission.'};emit(e);return Promise.resolve(snapshot(e));}
    if(!snapshot(e).canCancel)return Promise.resolve(snapshot(e));
    e.pending=true;stop(e);emit(e);
    const work=(async()=>{try{const payload=await api(`/api/project-copies/${encodeURIComponent(id)}/cancel`,{method:'POST',body:'{}'});if(!destroyed&&!receipt(e,payload?.operation)){unknown(e,'Cancellation is not confirmed.');await lookup(e);}}
      catch{if(!destroyed){unknown(e,'Cancellation is not confirmed.');await lookup(e);}}return snapshot(e);})();e.flight=work;
    return work.finally(()=>{if(e.flight===work){e.flight=null;e.pending=false;emit(e);poll(e);}}).then(()=>snapshot(e));
  }
  function recover() {
    if(destroyed)return Promise.resolve([]);if(recovery)return recovery;
    recovery=(async()=>{try{const payload=await api('/api/project-copies');if(!Array.isArray(payload?.operations)||!payload.operations.every(operationValid))throw Error();if(!destroyed){discoveryIssue='';for(const op of payload.operations)adopt(op);}}catch{discoveryIssue='Active project copies could not be checked. Check recovery before starting another copy.';}
      if(!destroyed)await Promise.all([...entries.values()].filter(e=>e.submitted&&busy(e)&&!e.pending).map(e=>check(e.op.operation_token)));
      return [...entries.values()].map(snapshot);})();return recovery.finally(()=>{recovery=null;});
  }
  return {start,get:id=>snapshot(entries.get(id)),forSource:id=>{const found=[...entries.values()].filter(e=>e.op.source_project_id===id);return snapshot(found.find(busy)||found.at(-1));},
    active:()=>[...entries.values()].filter(busy).map(snapshot),check,retry,cancel,recover,observe:adopt,
    destroy(){if(destroyed)return;destroyed=true;for(const e of entries.values())stop(e);}};
}
