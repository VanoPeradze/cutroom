/* One set of native editing commands; this module only lays them out and
   scrolls track rows. It never changes a cut, playhead, source or project. */
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
export function stripMode(width) { return width <= 0 || width >= 900 ? 'wide' : width < 600 ? 'small' : 'medium'; }

// Use the canvas's native row positions. Empty space above the first lane is
// its ruler, not a track. A partially visible lane is included in the count.
export function trackWindow(rows, value, height, extent) {
  const valid = rows.filter(r => Number.isFinite(r.top) && Number.isFinite(r.height) && r.height > 0)
    .slice().sort((a,b) => a.top-b.top);
  const max = Math.max(0, extent-height), at = clamp(value, 0, max);
  const visible = valid.map((r,i) => r.top+r.height > at+.5 && r.top < at+height-.5 ? i+1 : 0).filter(Boolean);
  const down = valid.find(r => r.top >= at+height*.65)?.top ?? max;
  const up = valid.filter(r => r.top <= at-height*.65).at(-1)?.top ?? 0;
  return {total:valid.length, first:visible[0]||0, last:visible.at(-1)||0,
    max, at, up:at <= 1 ? 0 : clamp(up,0,max), down:at >= max-1 ? max : clamp(down,0,max)};
}
export function railWheel(event, view) {
  if (!view || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
      !Number.isFinite(event.deltaY) || !event.deltaY || Math.abs(event.deltaX||0) >= Math.abs(event.deltaY)) return null;
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? view.clientHeight : 1;
  const at = clamp(view.scrollTop+event.deltaY*unit,0,Math.max(0,view.scrollHeight-view.clientHeight));
  return Math.abs(at-view.scrollTop) > .01 ? at : null;
}

const words={
  en:{controls:'Controls',title:'Timeline controls',close:'Close',view:'Timeline zoom',actions:'Edit actions',target:'Edit target',tracks:'Tracks',up:'Show earlier tracks',down:'Show later tracks'},
  he:{controls:'בקרים',title:'בקרי ציר הזמן',close:'סגירה',view:'תצוגת ציר הזמן',actions:'פעולות עריכה',target:'יעד עריכה',tracks:'ערוצים',up:'הצגת ערוצים קודמים',down:'הצגת ערוצים נוספים'}
};

export function initTimelineCommandStrip(doc, win) {
  const panel=doc?.getElementById('advancedPanel'), dock=doc?.getElementById('studioTimelineDock');
  if (panel?.timelineStripController) return panel.timelineStripController;
  const toolbar=dock?.querySelector('.editor-toolbar-main'), nav=dock?.querySelector('.timeline-navigation'),
    form=nav?.querySelector('.timeline-timecode-form'), scroll=doc?.getElementById('timelineScroll'),
    rail=dock?.querySelector('.timeline-track-headers'), rows=rail?.querySelector('.timeline-track-rows'),
    zoom=toolbar?.querySelector('.timeline-zoom-controls'), toolGroup=toolbar?.querySelector('.timeline-tools');
  if (!panel?.classList.contains('console-ready') || !toolbar || !nav || !form || !scroll || !rows || !zoom || !toolGroup) return null;
  const make=(tag,cls,id)=>{const e=doc.createElement(tag);if(cls)e.className=cls;if(id)e.id=id;return e;};
  const dialog=make('dialog','timeline-command-dialog','timelineCommandDialog');
  if (typeof dialog.showModal!=='function') return null; // Preserve the fully native original toolbar.
  const button=(cls,id)=>{const b=make('button',cls,id);b.type='button';return b;};
  const trigger=button('timeline-command-trigger','timelineCommandTrigger');
  trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls',dialog.id);trigger.setAttribute('aria-expanded','false');
  const heading=make('h2','','timelineCommandTitle'), close=button('command-close','timelineCommandClose');
  const header=make('header','command-heading');header.append(heading,close);dialog.append(header);dialog.setAttribute('aria-labelledby',heading.id);
  const groups={};for(const key of ['target','view','actions']){
    const group=make('section','command-section command-'+key),h=make('h3','','timelineCommand-'+key),body=make('div','command-items');
    group.setAttribute('aria-labelledby',h.id);group.append(h,body);dialog.append(group);groups[key]={group,h,body};
  }
  const items=[['timelineTargetField','target'],['manualDelete','actions'],['reviewSourceButton','actions'],['closeTimelineGaps','actions'],['editorMoreButton','actions']]
    .map(([id,key])=>[doc.getElementById(id),key]);
  items.push([zoom,'view']);if(items.some(([n])=>!n || n.parentElement!==toolbar))return null;
  const homes=items.map(([node,key])=>{const mark=doc.createComment('Original timeline command position');toolbar.insertBefore(mark,node);return {node,key,mark};});
  trigger.hidden=true;toolbar.append(trigger,dialog);
  const pager=make('div','timeline-track-pager','timelineTrackPager'), tagline=make('span','track-pager-name'), range=make('span','track-pager-count','timelineTrackRange'), announcement=make('span','sr-only');
  const up=button('track-pager-up','timelineTracksUp'),down=button('track-pager-down','timelineTracksDown');
  pager.setAttribute('role','group');up.setAttribute('aria-controls',scroll.id);down.setAttribute('aria-controls',scroll.id);
  up.setAttribute('aria-describedby',range.id);down.setAttribute('aria-describedby',range.id);announcement.setAttribute('role','status');announcement.setAttribute('aria-live','polite');
  pager.append(tagline,range,up,down,announcement);nav.insertBefore(pager,form);
  let mode=null,frame=null,dead=false,language='',speak=false,observers=[],subs=[];
  const listen=(node,type,fn,opts)=>{node.addEventListener(type,fn,opts);subs.push(()=>node.removeEventListener(type,fn,opts));};
  const focus=n=>n?.focus({preventScroll:true}), active=()=>!panel.hidden && doc.body.classList.contains('studio-open');
  function labels(){
    const lang=(doc.documentElement.lang||'en').split('-')[0], w=words[lang]||words.en;
    if(language===lang)return;language=lang;
    trigger.textContent=w.controls;trigger.setAttribute('aria-label',w.title);heading.textContent=w.title;close.textContent=w.close;
    for(const k of Object.keys(groups))groups[k].h.textContent=w[k];
    tagline.textContent=w.tracks;pager.setAttribute('aria-label',w.tracks);
    for(const [b,key] of [[up,'up'],[down,'down']]){b.title=w[key];b.setAttribute('aria-label',w[key]);}
  }
  const closeSheet=()=>{if(dialog.open)dialog.close();trigger.setAttribute('aria-expanded','false');};
  function layout() {
    if(dead)return;labels();
    const next=active()?stripMode(win.innerWidth):'wide';
    if(next===mode)return;
    const was=doc.activeElement,wasInSheet=dialog.contains(was),wasOnTrigger=was===trigger;
    if(dialog.open)closeSheet();mode=next;
    const compact=mode!=='wide';panel.dataset.timelineStrip=mode;
    for(const {node,key,mark} of homes){
      const move=compact && (key!=='view'||mode==='small'), parent=move?groups[key].body:toolbar;
      if(node.parentNode!==parent){if(move)parent.append(node);else toolbar.insertBefore(node,mark);}
    }
    groups.view.group.hidden=mode!=='small';trigger.hidden=!compact;
    if(active() && was && (wasInSheet||wasOnTrigger||homes.some(h=>h.node.contains(was)))){
      if(compact && (dialog.contains(was)||wasOnTrigger))focus(trigger);
      else if(wasInSheet && !dialog.contains(was))focus(was);
      else if(!compact && (wasOnTrigger||wasInSheet))focus(doc.getElementById('editorMoreButton'));
    }
  }
  const geometry=()=>trackWindow([...rows.querySelectorAll('.track-header')].map(r=>({top:parseFloat(r.style.top),height:parseFloat(r.style.height)})),
    scroll.scrollTop,scroll.clientHeight,scroll.scrollHeight);
  function paint(){
    if(dead)return;layout();if(!active())return;
    // The compact grid is one vertically scrolling surface. Reserve actual command
    // rows plus a useful strip of lanes, even when range hints or labels wrap.
    // Do not change the saved desktop divider height or its monitor allocation.
    if(mode!=='wide'){
      // Mirror the existing controller's INLINE numeric preference. CSS uses the
      // larger of that value and this floor only on a stacked timeline; the
      // approved desktop geometry/style and its saved preference remain intact.
      const native=panel.style.getPropertyValue('--workspace-timeline-height')||'256px';
      if(panel.style.getPropertyValue('--timeline-command-natural-height')!==native)panel.style.setProperty('--timeline-command-natural-height',native);
      const offset=scroll.getBoundingClientRect().top-dock.getBoundingClientRect().top;
      const desired=Math.ceil(offset+(win.innerHeight>=700?156:134)+(parseFloat(win.getComputedStyle(dock).paddingBottom)||0)+2)+'px';
      if(panel.style.getPropertyValue('--timeline-command-min-height')!==desired)panel.style.setProperty('--timeline-command-min-height',desired);
    }else for(const name of ['--timeline-command-min-height','--timeline-command-natural-height'])if(panel.style.getPropertyValue(name))panel.style.removeProperty(name);
    const g=geometry(),show=g.total>0 && scroll.clientHeight>0 && g.max>1,focused=doc.activeElement;
    if(!show && pager.contains(focused))focus(doc.getElementById('timelineIndexButton'));
    pager.hidden=!show;if(!show)return;
    const count=g.first===g.last?String(g.first):g.first+'–'+g.last;
    const value=g.first?count+' / '+g.total:String(g.total);if(range.textContent!==value)range.textContent=value;
    if(speak){announcement.textContent=(words[language]||words.en).tracks+' '+value;speak=false;}
    up.disabled=g.at<=1;down.disabled=g.at>=g.max-1;
    if(focused===up&&up.disabled&&!down.disabled)focus(down);
    if(focused===down&&down.disabled&&!up.disabled)focus(up);
  }
  const queue=()=>{if(!dead&&frame===null)frame=win.requestAnimationFrame(()=>{frame=null;paint();});};
  listen(trigger,'click',()=>{if(mode==='wide'||!active()||dialog.open||doc.querySelector('dialog[open]'))return;dialog.showModal();trigger.setAttribute('aria-expanded','true');focus(close);});
  listen(close,'click',closeSheet);
  listen(dialog,'close',()=>{trigger.setAttribute('aria-expanded',String(dialog.open));});
  listen(dialog,'click',event=>{
    // Let the existing native command be the only receiver of the click.
    // Dismiss first so it can open its own confirmation/inspector freely.
    const b=event.target.closest?.('button');
    if(b&&!b.disabled&&groups.actions.body.contains(b))closeSheet();
    else if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeSheet();}
  },true);
  const scrollTracks=top=>{
    scroll.scrollTop=top;
    // Align names in this same interaction frame instead of waiting for delivery
    // of the native scroll event. TimelineView continues to own all other scrolling.
    rows.style.transform='translateY('+(-scroll.scrollTop)+'px)';queue();
  };
  for(const [b,dir] of [[up,'up'],[down,'down']])listen(b,'click',()=>{speak=true;scrollTracks(geometry()[dir]);});
  listen(rail,'wheel',e=>{const y=railWheel(e,scroll);if(y!==null&&e.cancelable){e.preventDefault();scrollTracks(y);}},{passive:false});
  listen(scroll,'scroll',queue,{passive:true});listen(win,'resize',queue,{passive:true});
  const observe=(target,options)=>{const o=new win.MutationObserver(queue);o.observe(target,options);observers.push(o);};
  observe(doc.documentElement,{attributes:true,attributeFilter:['lang','dir']});observe(doc.body,{attributes:true,attributeFilter:['class']});
  observe(panel,{attributes:true,attributeFilter:['class','hidden','style']});observe(rows,{childList:true});
  if(win.ResizeObserver){const o=new win.ResizeObserver(queue);o.observe(scroll);o.observe(toolbar);o.observe(nav);const hint=doc.getElementById('timelineCutStatus');if(hint)o.observe(hint);o.observe(doc.getElementById('timelineCanvas'));observers.push(o);}
  paint();
  const controller={sync:paint,destroy(){
    if(dead)return;dead=true;closeSheet();if(frame!==null)win.cancelAnimationFrame(frame);
    subs.forEach(f=>f());observers.forEach(o=>o.disconnect());
    for(const {node,mark} of homes){toolbar.insertBefore(node,mark);mark.remove();}
    if(dialog.contains(doc.activeElement)||doc.activeElement===trigger)focus(doc.getElementById('editorMoreButton'));
    else if(pager.contains(doc.activeElement))focus(doc.getElementById('timelineIndexButton'));
    trigger.remove();dialog.remove();pager.remove();panel.style.removeProperty('--timeline-command-min-height');panel.style.removeProperty('--timeline-command-natural-height');delete panel.dataset.timelineStrip;delete panel.timelineStripController;
  }};panel.timelineStripController=controller;return controller;
}
if(typeof document!=='undefined'){
  const start=()=>{const panel=document.getElementById('advancedPanel');if(!panel||initTimelineCommandStrip(document,window))return;
    const o=new MutationObserver(()=>{if(initTimelineCommandStrip(document,window))o.disconnect();});
    o.observe(panel,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
}
