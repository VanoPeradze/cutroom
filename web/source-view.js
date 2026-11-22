/* Source viewing is navigation. The original pool commands and the mounted
   media element keep their owners, readiness, decoders and local marks. */
const assetPattern=/^asset_[0-9a-f]{32}$/;
export function poolSourceKind(data,assetId){
  if(typeof assetId!=='string'||!assetPattern.test(assetId))return '';
  if(data?.reviewShot===assetId && !data.reviewAudio)return 'video';
  if(data?.reviewAudio===assetId && !data.reviewShot)return 'audio';
  return '';
}
export function sourceFocusContinuation(previous,next,mediaRoom,programPlaying){
  return Boolean(mediaRoom&&!programPlaying&&previous?.focused&&previous.project&&previous.project===next?.project&&next?.video);
}
const labels={
  en:{source:'Open source',more:'Actions',focus:'Focus source',back:'Split view',sourceName:'Source',solo:'Original picture and sound. Edited effects are not shown.',clip:'Source marks & placement',busy:'Finish the current operation before focusing the source.'},
  he:{source:'פתיחת מקור',more:'פעולות',focus:'הגדלת המקור',back:'תצוגה מפוצלת',sourceName:'מקור',solo:'תמונה ושמע מהמקור, ללא האפקטים של העריכה.',clip:'סימוני המקור ומיקום בעריכה',busy:'יש לסיים את הפעולה הנוכחית לפני הגדלת המקור.'}
};
const words=doc=>labels[(doc.documentElement.lang||'en').split('-')[0]]||labels.en;
const setText=(n,v)=>{if(n.textContent!==v)n.textContent=v;};

export function initSourceView(doc,win){
  const panel=doc?.getElementById('advancedPanel'),media=doc?.getElementById('studioPanelMedia'),shelf=doc?.getElementById('studioShelfMedia'),
    inspector=doc?.getElementById('studioInspector'),program=doc?.getElementById('previewStage');
  if(panel?.sourceViewController)return panel.sourceViewController;
  if(!panel?.classList.contains('console-ready')||!media||!shelf||!inspector||!program)return null;
  const create=(tag,cls)=>{const n=doc.createElement(tag);if(cls)n.className=cls;return n;};
  const records=new Map(),listeners=[],observers=[];
  const listen=(e,t,f,opt)=>{e.addEventListener(t,f,opt);listeners.push(()=>e.removeEventListener(t,f,opt));};
  let active=null,nextFrame=null,dead=false;
  const mediaRoom=()=>!panel.hidden && !panel.inert && panel.dataset.workspace==='media' && inspector.dataset.workbenchPane!=='ai' && !media.hidden;
  const programPlaying=()=>program.classList.contains('playing');
  function releaseCard(card,v){
    if(v.mark.parentNode){v.mark.parentNode.insertBefore(v.button,v.mark);v.mark.remove();}
    v.button.textContent=v.oldText;for(const [key,value] of Object.entries(v.attrs)){if(value===null)v.button.removeAttribute(key);else v.button.setAttribute(key,value);}
    if(v.caption)v.caption.textContent=v.oldCaption;
    delete v.button.dataset.poolSource;delete card.dataset.directSource;delete card.dataset.sourceCurrent;
  }
  function syncPool(){
    // Cards are recreated by the library. Never keep removed media or fabricate
    // equivalent actions. A disabled or mismatched native command stays unavailable.
    for(const [card,v] of records)if(!shelf.contains(card)){records.delete(card);}
    const w=words(doc),current=mediaRoom()?media.querySelector(':scope > .library-source-monitor[data-source-asset-id]'):null;
    for(const card of shelf.querySelectorAll('.media-asset[data-library-asset]')){
      let v=records.get(card);
      if(!v){
        const assetId=card.dataset.libraryAsset,details=card.querySelector(':scope > .console-asset-actions'),content=details?.querySelector('.console-asset-action-body');
        const matches=content?[...content.querySelectorAll('button[data-review-shot],button[data-review-audio]')].filter(n=>poolSourceKind(n.dataset,assetId)):[];
        if(matches.length!==1)continue;
        const b=matches[0], mark=doc.createComment('Native In / Out command home'),caption=details.querySelector('summary > span');
        const attrs=Object.fromEntries(['aria-label','title','aria-current'].map(k=>[k,b.getAttribute(k)]));
        v={button:b,mark,attrs,oldText:b.textContent,caption,oldCaption:caption?.textContent,assetId,kind:poolSourceKind(b.dataset,assetId)};
        b.parentNode.insertBefore(mark,b);card.insertBefore(b,details);
        b.dataset.poolSource=v.kind;card.dataset.directSource=v.kind;records.set(card,v);
      }
      const name=card.querySelector(':scope > span:not(.library-thumb)')?.textContent?.trim()||v.attrs['aria-label']?.replace(/^.*?:\s*/,'')||w.sourceName;
      setText(v.button,w.source);const label=w.source+': '+name;if(v.button.getAttribute('aria-label')!==label)v.button.setAttribute('aria-label',label);
      if(v.caption)setText(v.caption,w.more);
      // An existing disabled reason is more important than a generic tooltip.
      if(!v.button.disabled && !v.button.title)v.button.title=label;
      const isCurrent=current?.dataset.sourceAssetId===v.assetId;
      if(isCurrent){card.dataset.sourceCurrent='true';v.button.setAttribute('aria-current','true');}
      else{delete card.dataset.sourceCurrent;v.button.removeAttribute('aria-current');}
    }
  }
  function setFocus(on,{returnFocus=false,restoreScroll=false}={}){
    const v=active;if(!v||dead||v.focused===on)return false;
    if(on && (!mediaRoom()||!v.root.isConnected||v.root.admitSourceFocus?.()!==true)){
      if(v.root.isConnected)setText(v.notice,words(doc).busy);return false;
    }
    if(on){
      v.before={panel:panel.scrollTop,inspector:inspector.scrollTop};
      v.focused=true;panel.dataset.sourceView='focus';v.root.dataset.sourceView='focus';
      // The original VIDEO, its parent and its src are untouched. No player
      // enters a dialog, fullscreen, or a second decoding context.
      panel.scrollTop=0;inspector.scrollTop=0;v.controls.scrollTop=0;
    }else{
      v.focused=false;delete v.root.dataset.sourceView;delete panel.dataset.sourceView;
      if(restoreScroll&&v.before){panel.scrollTop=v.before.panel;inspector.scrollTop=v.before.inspector;}
    }
    const w=words(doc);setText(v.toggle,on?w.back:w.focus);v.toggle.setAttribute('aria-pressed',String(on));setText(v.notice,'');
    if(returnFocus&&v.toggle.isConnected)v.toggle.focus({preventScroll:true});return true;
  }
  function detach(v){
    if(!v)return;v.off.forEach(f=>f());delete v.root.dataset.sourceView;
    // On controller teardown restore coupled original nodes in exact order.
    if(v.root.isConnected)for(const x of v.homes){if(x.mark.parentNode===v.root)v.root.insertBefore(x.n,x.mark);x.mark.remove();}
    v.controls.remove();v.toggle.remove();v.note.remove();v.notice.remove();if(active===v)active=null;
  }
  function attach(root){
    const header=root.querySelector(':scope > .library-source-monitor-header'),name=root.querySelector(':scope > .library-shot-name'),
      video=root.querySelector(':scope > video'),form=root.querySelector(':scope > form.library-shot-range');
    if(!header||!name||!video||!form||typeof root.admitSourceFocus!=='function')return null;
    const w=words(doc),toggle=create('button','source-view-toggle');toggle.type='button';toggle.dataset.sourceViewToggle='true';
    toggle.setAttribute('aria-pressed','false');toggle.setAttribute('aria-controls','studioPanelMedia');setText(toggle,w.focus);
    const close=header.querySelector('button[data-shot-keep]')||header.querySelector('button');header.insertBefore(toggle,close);
    const note=create('p','source-view-note');note.textContent=w.solo;const notice=create('p','source-view-notice');notice.setAttribute('role','status');
    const controls=create('div','source-view-controls');controls.setAttribute('role','group');controls.setAttribute('aria-label',w.clip);
    // Group controls once; do not move or rebuild the original media element.
    const keep=new Set([header,name,video,root.querySelector(':scope > .library-source-frame'),root.querySelector(':scope > .library-shot-match-origin')]);
    const homes=[...root.children].filter(n=>!keep.has(n)).map(n=>{const mark=doc.createComment('Source control position');root.insertBefore(mark,n);controls.append(n);return{n,mark};});
    root.append(controls,note,notice);
    const v={root,toggle,note,notice,controls,homes,off:[],project:root.dataset.sourceProjectId,asset:root.dataset.sourceAssetId,focused:false};
    const on=(el,t,f,opts)=>{el.addEventListener(t,f,opts);v.off.push(()=>el.removeEventListener(t,f,opts));};
    on(toggle,'click',()=>setFocus(!v.focused,{returnFocus:true,restoreScroll:true}));
    on(root,'keydown',e=>{if(v.focused&&e.key==='Escape'&&!e.defaultPrevented&&!e.isComposing&&!doc.fullscreenElement&&!doc.querySelector('dialog[open]')){
      e.preventDefault();e.stopImmediatePropagation();setFocus(false,{returnFocus:true,restoreScroll:true});
    }},true);
    return v;
  }
  function sync(){
    if(dead)return;const root=mediaRoom()?media.querySelector(':scope > .library-shot-review.library-source-monitor[data-source-asset-id]'):null;
    if(root!==active?.root){
      const previous=active?{focused:active.focused,project:active.project,before:active.before}:null;
      if(active){delete panel.dataset.sourceView;detach(active);}
      if(root){active=attach(root);if(active&&sourceFocusContinuation(previous,{project:active.project,video:true},mediaRoom(),programPlaying())&&setFocus(true))active.before=previous.before;}
    }
    if(active){
      if(active.focused&&programPlaying())setFocus(false); // Show the real Program monitor if the edit starts playing.
      const w=words(doc);setText(active.toggle,active.focused?w.back:w.focus);setText(active.note,w.solo);active.controls.setAttribute('aria-label',w.clip);
    }
    syncPool();
  }
  const queue=()=>{if(!dead&&nextFrame===null)nextFrame=win.requestAnimationFrame(()=>{nextFrame=null;sync();});};
  const observe=(n,options)=>{const o=new win.MutationObserver(queue);o.observe(n,options);observers.push(o);};
  observe(shelf,{childList:true,subtree:true});observe(media,{childList:true,attributes:true,attributeFilter:['hidden']});
  observe(inspector,{attributes:true,attributeFilter:['data-workbench-pane']});observe(panel,{attributes:true,attributeFilter:['data-workspace','hidden','inert']});
  observe(program,{attributes:true,attributeFilter:['class']});observe(doc.documentElement,{attributes:true,attributeFilter:['lang','dir']});
  // The explicit Close source command already returns focus. Reveal that same
  // owner after rerenders instead of leaving keyboard/touch users offscreen.
  listen(media,'click',e=>{const b=e.target.closest?.('.library-source-monitor [data-shot-keep],.audio-source-review [data-audio-close]');if(!b||b.disabled)return;
    const root=b.closest('.library-source-monitor'),id=root?.dataset.sourceAssetId;
    win.requestAnimationFrame(()=>{if(dead||!id||root.isConnected||!mediaRoom())return;const target=doc.activeElement;
      if(target?.dataset.poolSource && poolSourceKind(target.dataset,id))target.scrollIntoView({block:'nearest',inline:'nearest'});});
  },true);
  sync();const controller={sync,destroy(){if(dead)return;if(active?.focused)setFocus(false,{restoreScroll:true});dead=true;
    if(nextFrame!==null)win.cancelAnimationFrame(nextFrame);listeners.forEach(fn=>fn());observers.forEach(o=>o.disconnect());
    detach(active);for(const [card,v] of records)releaseCard(card,v);records.clear();delete panel.dataset.sourceView;delete panel.sourceViewController;
  }};panel.sourceViewController=controller;return controller;
}
if(typeof document!=='undefined'){
  const start=()=>{const p=document.getElementById('advancedPanel');if(!p||initSourceView(document,window))return;const o=new MutationObserver(()=>{if(initSourceView(document,window))o.disconnect();});
  o.observe(p,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
}
