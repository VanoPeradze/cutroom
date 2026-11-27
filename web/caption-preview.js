// Edited-clock ASS event semantics; browser shaping/collision geometry remains approximate.
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const finite = (value, min, max) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
const styles = new Set(['bold','clean','boxed','highlight','pop','box','neon','word','emphasis']);
const positions = new Set(['auto','top','center','bottom']);
const invalid = 'The caption preview is unavailable. Reload the current saved edit.';

export function captionPreviewIssue(scene) {
  if (!record(scene) || scene.version !== 1 || typeof scene.available !== 'boolean' || typeof scene.issue !== 'string'
    || typeof scene.project_id !== 'string' || !scene.project_id || !Number.isInteger(scene.revision) || scene.revision < 0
    || scene.clock !== 'edited') return invalid;
  if (!scene.available) return scene.issue || invalid;
  if (!finite(scene.width,1,16384) || !finite(scene.height,1,16384) || !finite(scene.fps,1,240)
    || !record(scene.settings) || !styles.has(scene.settings.caption_style) || !positions.has(scene.settings.caption_position)
    || !Number.isInteger(scene.settings.caption_scale) || !finite(scene.settings.caption_scale,75,150)
    || !Number.isInteger(scene.settings.caption_words_per_line) || !finite(scene.settings.caption_words_per_line,2,12)
    || !Array.isArray(scene.events) || scene.events.length > 200000) return invalid;
  const ids = new Set(), orders = new Set();
  for (const event of scene.events) {
    if (!record(event) || typeof event.id !== 'string' || !event.id || ids.has(event.id)
      || typeof event.export_item_id !== 'string' || !event.export_item_id || typeof event.selectable !== 'boolean' || typeof event.selection_issue !== 'string'
      || (event.selectable ? typeof event.item_id !== 'string' || !event.item_id || event.selection_issue !== '' : event.item_id !== null || !event.selection_issue.trim())
      || !finite(event.start,0,86400) || !finite(event.end,0,86400)
      || event.end <= event.start || typeof event.text !== 'string' || !event.text || event.text.length > 100000
      || !styles.has(event.style) || !positions.has(event.position) || !Number.isInteger(event.scale) || !finite(event.scale,75,150)
      || !(event.layout === null || typeof event.layout === 'string') || !finite(event.font_size,1,1000)
      || !finite(event.margin_v,0,16384) || !finite(event.outline,0,1000) || !finite(event.shadow,0,1000)
      || typeof event.positioned !== 'boolean' || ![2,5,8].includes(event.alignment) || event.layer !== 0
      || !Number.isInteger(event.order) || event.order < 0 || orders.has(event.order)
      || event.positioned && (!finite(event.x,0,scene.width) || !finite(event.y,0,scene.height))) return invalid;
    if (event.tokens === null) { if (event.active_index !== null) return invalid; }
    else if (!Array.isArray(event.tokens) || !event.tokens.length || event.tokens.length > 1000
      || event.tokens.some(token => typeof token !== 'string' || !token || token.length > 100000)
      || !Number.isInteger(event.active_index) || event.active_index < 0 || event.active_index >= event.tokens.length) return invalid;
    ids.add(event.id); orders.add(event.order);
  }
  return scene.issue || '';
}

// Interval tree avoids scanning a whole transcript on every playback frame or seek.
function eventTree(events) {
  const ordered = [...events].sort((a,b)=>a.start-b.start || a.order-b.order);
  function build(lo,hi) {
    if(lo>=hi)return null;
    const mid=(lo+hi)>>1,left=build(lo,mid),right=build(mid+1,hi),event=ordered[mid];
    return {event,left,right,maxEnd:Math.max(event.end,left?.maxEnd||0,right?.maxEnd||0)};
  }
  return build(0,ordered.length);
}
function activeEvents(tree,time,result=[]) {
  if(!tree || tree.maxEnd<=time)return result;
  activeEvents(tree.left,time,result);
  if(tree.event.start<=time){if(time<tree.event.end)result.push(tree.event);activeEvents(tree.right,time,result);}
  return result;
}

export function initCaptionPreview(stage, primary, {select} = {}) {
  const doc=primary.ownerDocument, records=[];
  let destroyed=false,original=null,cached=null,canonical=null,tree=null,cachedIssue='',layoutKey='',replay=null;
  let dimensions=[stage.clientWidth,stage.clientHeight];
  const Observer=doc.defaultView?.ResizeObserver;
  const observer=typeof Observer==='function'?new Observer(()=>{
    if(destroyed || !replay)return;
    const next=[stage.clientWidth,stage.clientHeight];
    if(next[0]===dimensions[0] && next[1]===dimensions[1])return;
    const current=replay;render(current.scene,current.time,current.options);
  }):null;
  observer?.observe(stage);
  const snapshot=()=>Array.from(primary.attributes,attr=>[attr.name,attr.value]);
  function restore() {
    if(original){for(const attr of Array.from(primary.attributes))primary.removeAttribute(attr.name);for(const [name,value]of original)primary.setAttribute(name,value);original=null;}
    primary.replaceChildren();primary.hidden=true;
  }
  function release() {
    for(const row of records){row.node.removeEventListener('pointerdown',row.down);row.node.removeEventListener('click',row.click);if(row.node!==primary)row.node.remove();}
    records.length=0;layoutKey='';restore();
  }
  function clear(){replay=null;release();cached=null;canonical=null;tree=null;cachedIssue='';}
  function make(index) {
    if(!original)original=snapshot();
    const node=index===0?primary:doc.createElement('div');
    node.classList.add('preview-caption');node.setAttribute('data-caption-cue','');
    node.setAttribute('dir','auto');
    const row={node,event:null,contentKey:'',styleKey:'',down:event=>event.stopPropagation(),click:event=>{
      event.stopPropagation();if(!destroyed && !node.hidden && row.event?.selectable)select?.(row.event.item_id);
    }};
    node.addEventListener('pointerdown',row.down);node.addEventListener('click',row.click);
    if(index>0)primary.parentNode.append(node);
    records.push(row);return row;
  }
  function content(row,event) {
    const key=JSON.stringify([event.text,event.tokens,event.active_index,event.keywords]);
    if(row.contentKey===key)return;
    row.contentKey=key;
    if(event.tokens===null)row.node.textContent=event.text;
    else row.node.replaceChildren(...event.tokens.flatMap((token,index)=>{
      const span=doc.createElement('span');span.textContent=token;
      if(index===event.active_index)span.classList.add('caption-active-word');
      else if(Array.isArray(event.keywords)&&event.keywords.includes(index))span.classList.add('caption-keyword');
      return index?[' ',span]:[span];
    }));
  }
  function position(row,event,width,height,scene) {
    const sx=width/scene.width,sy=height/scene.height,font=event.font_size*sy,outline=event.outline*sy,shadow=event.shadow*sy;
    const anchor=event.positioned?event.y*sy:event.alignment===8?event.margin_v*sy:event.alignment===5?height/2:height-event.margin_v*sy;
    const x=event.positioned?event.x*sx:width/2,margin=42*sx;
    const cueWidth=Math.max(1,width-2*margin),vertical=event.alignment===8?'0%':event.alignment===5?'-50%':'-100%';
    const s=row.node.style;
    Object.assign(s,{position:'absolute',fontFamily:'Arial, sans-serif',fontSize:`${font}px`,fontWeight:event.style==='clean'?'400':'700',lineHeight:'1.15',
      left:`${x}px`,right:'auto',width:'max-content',maxWidth:`${cueWidth}px`,top:`${anchor}px`,bottom:'auto',
      transform:`translate(-50%, ${vertical})`,transformOrigin:'center center',textAlign:'center',margin:'0',padding:'0',border:'0',borderRadius:'0',
      color:'#fff',background:event.style==='boxed'?'rgb(8,16,19)':'transparent',boxShadow:event.style==='boxed'?`0 0 0 ${outline}px rgb(8,16,19)`:'none',whiteSpace:'pre-line',overflowWrap:'break-word',
      textShadow:shadow?`${shadow}px ${shadow}px 0 rgba(0,0,0,.5)`:'none',webkitTextStroke:event.style==='boxed'?'0':`${outline}px ${event.style==='clean'?'rgba(0,0,0,.15)':event.style==='bold'?'rgba(0,0,0,.2)':'#000'}`,
      paintOrder:'stroke fill',pointerEvents:'auto'});
    s.setProperty('--caption-preview-scale','1');s.setProperty('--caption-event-top',`${anchor}px`);s.setProperty('--caption-event-bottom','auto');
    s.setProperty('--caption-event-font-size',`${font}px`);s.setProperty('--caption-event-outline',`${outline}px`);s.setProperty('--caption-event-shadow',`${shadow}px`);
    row.anchor=anchor;
  }
  function collide(active) {
    // This is deliberately a browser-bounds approximation, not libass geometry.
    // Recompute from canonical order and original anchors on every active-set change.
    const occupied=[];let approximate=false;
    for(const row of active){
      if(row.event.positioned)continue;
      let box=row.node.getBoundingClientRect(),shift=0;
      for(let attempt=0;attempt<=occupied.length;attempt++){
        const hit=occupied.find(other=>box.left<other.right&&box.right>other.left&&box.top<other.bottom&&box.bottom>other.top);
        if(!hit)break;
        const delta=row.event.alignment===8?hit.bottom-box.top:hit.top-box.bottom;
        shift+=delta;box={...box,left:box.left,right:box.right,top:box.top+delta,bottom:box.bottom+delta};approximate=true;
      }
      if(shift){row.node.style.top=`${row.anchor+shift}px`;row.node.style.setProperty('--caption-event-top',`${row.anchor+shift}px`);}
      occupied.push(box);
    }
    return approximate;
  }
  function render(scene,time,{projectId,revision,selectedId=null,enabled=true}={}) {
    const unavailable=issue=>{replay=null;release();return {available:false,issue,activeCount:0,collisionApproximate:false};};
    if(destroyed)return {available:false,issue:'Caption preview is closed.',activeCount:0,collisionApproximate:false};
    if(!scene || scene.project_id!==projectId || scene.revision!==revision || !Number.isFinite(time))return unavailable(invalid);
    if(cached!==scene){
      cached=scene;cachedIssue=captionPreviewIssue(scene);
      // Accepted scenes are saved immutable snapshots. Keep our own event values
      // so a caller cannot mutate already-validated text/geometry behind the index.
      canonical=cachedIssue?null:{...scene,events:scene.events.map(event=>({...event,tokens:event.tokens?.slice()??null}))};
      tree=canonical?eventTree(canonical.events):null;layoutKey='';
    }
    if(cachedIssue)return unavailable(cachedIssue);
    if(!enabled){replay=null;release();return {available:true,issue:'',activeCount:0,collisionApproximate:false};}
    replay={scene,time,options:{projectId,revision,selectedId,enabled}};
    const events=activeEvents(tree,time).sort((a,b)=>a.order-b.order),width=stage.clientWidth,height=stage.clientHeight;
    dimensions=[width,height];
    if(!(width>0&&height>0)){release();return {available:true,issue:'',activeCount:0,collisionApproximate:false};}
    const key=JSON.stringify([width,height,events.map(event=>event.id)]),relayout=key!==layoutKey;
    for(let index=0;index<events.length;index++){
      const event=events[index],row=records[index]||make(index);row.event=event;row.node.hidden=false;
      const meta=JSON.stringify([event.item_id,event.export_item_id,event.selectable,event.selection_issue,event.style,event.position,event.layout]);
      if(row.meta!==meta){
        if(event.selectable)row.node.dataset.captionId=event.item_id;else row.node.removeAttribute('data-caption-id');
        row.node.title=!event.selectable?event.selection_issue:event.export_item_id!==event.item_id?'Select the related editor subtitle. Export-aligned boundary words may differ from the editor line.':'Select this subtitle in the editor.';
        row.node.dataset.captionStyle=event.style;row.node.dataset.captionPosition=event.position;row.node.dataset.captionLayout=event.layout||'';row.meta=meta;
      }
      const selected=event.selectable && event.item_id===selectedId;if(row.selected!==selected){row.node.classList.toggle('caption-selected',selected);row.selected=selected;}
      content(row,event);if(relayout)position(row,event,width,height,canonical);
    }
    for(let index=events.length;index<records.length;index++){records[index].node.hidden=true;records[index].event=null;}
    if(!events.length)primary.hidden=true;
    if(relayout){render.approximate=collide(records.slice(0,events.length));layoutKey=key;}
    return {available:true,issue:'',activeCount:events.length,collisionApproximate:Boolean(render.approximate)};
  }
  return {render,clear,destroy(){if(destroyed)return;clear();destroyed=true;observer?.disconnect();}};
}
