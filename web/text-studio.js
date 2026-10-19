// User-authored text lives on the edit clock, independently of the AI transcript.
const TEXT_TEMPLATES = [
  {id:'plain',name:'Plain text',detail:'Text at your chosen position.'},
  {id:'lower_third',name:'Lower third',detail:'Name and optional second line, fixed at the lower left.'},
  {id:'chapter',name:'Chapter card',detail:'A centered heading with an optional second line.'},
  {id:'callout',name:'Callout',detail:'A boxed note, fixed at the upper left.'},
  {id:'highlight',name:'Highlight',detail:'Yellow emphasis at your chosen position.'},
];
export function textStyle(clip, width, height, previewHeight) {
  const base = Math.max(28, Math.min(72, Math.round(height * (height >= width ? .048 : .042))));
  const size = Math.max(20, Math.min(108, Math.round(base * (clip.scale || 100) / 100)));
  const ratio = previewHeight / height;
  const stroke = clip.style === 'bold' ? Math.max(2, Math.round(size * .09)) : Math.max(1, Math.round(size * .055));
  return {font: size * ratio, stroke: stroke * ratio, margin: Math.max(32, Math.round(height * .075)) * ratio,
    horizontal:42 / width * 100, box:Math.max(3,Math.round(size*.12))*ratio};
}

export class TextStudio {
  constructor(root, stage, options) {
    this.root=root; this.stage=stage; this.options=options; this.projectId=null; this.selected=null;
    this.pending=new Map(); this.overrides=new Map(); this.dragOverrides=new Map(); this.saving=null; this.timer=null; this.importing=false; this.limit=100;
    root.innerHTML=`<div class="text-studio-head"><h4>Your text & captions</h4></div>
      <div class="text-actions"><button type="button" data-add="title">Add text</button><button type="button" data-add="caption">Add caption</button></div>
      <details class="text-import inspector-section"><summary>Import caption file</summary><button type="button" data-import>Choose SRT / VTT</button>
      <input type="file" accept=".srt,.vtt" aria-label="Import captions file" hidden>
      <label class="text-replace"><input type="checkbox" data-replace> Replace my existing custom captions when importing</label>
      <p class="text-help">Times refer to the edited video, not the original recording. Imported text does not replace the AI transcript. Turn off AI subtitles below if you do not want both.</p></details>
      <p class="text-status" role="status" aria-live="polite">Text appears on its own timeline lane and is included in the video.</p>
      <div class="text-recovery" hidden><button type="button" data-retry>Retry save</button><button type="button" data-discard>Discard unsaved text changes</button></div>
      <label class="text-search">Find custom text<input type="search" data-search placeholder="Search titles and captions"></label>
      <div class="text-clip-list" aria-label="Custom titles and captions"></div><button type="button" data-more hidden>Show more</button>
      <p class="text-selection-empty">Select custom text from the list to edit its template and timing.</p>
      <section class="text-inspector" hidden data-editor-shortcuts="off"><h4>Edit selected text</h4>
        <label>Text<textarea data-text="text" dir="auto" rows="3" maxlength="1000"></textarea></label>
        <section class="text-template-section" aria-label="Text template">
          <h5>Template</h5>
          <div class="text-template-picker" role="radiogroup" aria-label="Text template" aria-describedby="textTemplateDescription">${TEXT_TEMPLATES.map((template,index)=>`<button type="button" data-template-choice="${template.id}" role="radio" aria-checked="${index===0}" tabindex="${index===0?0:-1}"><span class="text-template-mark" aria-hidden="true">Aa</span><span>${template.name}</span></button>`).join('')}</div>
          <p class="text-template-description" id="textTemplateDescription"></p>
          <select data-text="template" hidden aria-label="Text template">${TEXT_TEMPLATES.map(template=>`<option value="${template.id}">${template.name}</option>`).join('')}</select>
        </section>
        <div class="text-fields"><label>Start (seconds)<input type="number" data-text="start" min="0" step="0.01"></label><label>End (seconds)<input type="number" data-text="end" min="0.08" step="0.01"></label>
        <label data-template-field="subtext">Second line<input type="text" data-text="subtext" dir="auto" maxlength="200" placeholder="Role, label or date"></label>
        <label data-template-field="position">Position<select data-text="position"><option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option></select></label>
        <label>Style<select data-text="style"><option value="clean">Clean</option><option value="bold">Bold</option><option value="boxed">Boxed</option></select></label>
        <label>Size (%)<input type="number" data-text="scale" min="75" max="150" step="5"></label></div>
        <div class="text-actions"><button type="button" data-preview>Preview at start</button><button type="button" data-remove>Remove text</button></div>
        <p class="text-help">Changes preview immediately and save automatically. Drag this text clip or its edges on the timeline. Simultaneous text in the same position can overlap.</p>
      </section>`;
    this.status=root.querySelector('.text-status'); this.inspector=root.querySelector('.text-inspector');
    this.emptySelection=root.querySelector('.text-selection-empty');
    this.templatePicker=root.querySelector('.text-template-picker'); this.templateDescription=root.querySelector('.text-template-description');
    this.layer=document.createElement('div'); this.layer.className='custom-text-layer'; this.layer.setAttribute('aria-hidden','true'); stage.append(this.layer);
    const onClick=event=>{
      const button=event.target.closest('button'); if(!button)return;
      if(button.dataset.templateChoice) this.chooseTemplate(button.dataset.templateChoice);
      else if(button.dataset.add) void this.add(button.dataset.add);
      else if(button.hasAttribute('data-import')) this.find('input[type=file]').click();
      else if(button.dataset.textId) void this.select(button.dataset.textId,true);
      else if(button.hasAttribute('data-retry')) void this.flush();
      else if(button.hasAttribute('data-discard')) { if(!this.saving){this.pending.clear();this.overrides.clear();this.render(true);this.options.preview();this.status.textContent='Unsaved text changes discarded.';} }
      else if(button.hasAttribute('data-remove')) void this.action('text_remove',{clip_id:this.selected});
      else if(button.hasAttribute('data-preview')) { const clip=this.clips().find(c=>c.id===this.selected);if(clip)this.options.seek(clip.start); }
      else if(button.hasAttribute('data-more')) {this.limit+=100;this.renderList();}
    };
    root.addEventListener('click',onClick);
    root.querySelector('input[type=file]').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)void this.importFile(file);});
    root.querySelector('[data-search]').addEventListener('input',()=>{this.limit=100;this.renderList();});
    root.addEventListener('input',event=>{
      const key=event.target.dataset.text; if(!key||!this.selected)return;
      const value=['start','end','scale'].includes(key) ? (event.target.value==='' ? NaN : Number(event.target.value)) : event.target.value;
      if(key==='template')this.renderTemplates(value);
      this.queueClip(this.selected,{[key]:value});
    });
    this.templatePicker.addEventListener('keydown',event=>this.templateKeydown(event));
    this.observer=new ResizeObserver(()=>this.options.preview()); this.observer.observe(stage);
    this.libraryRoot=options.libraryRoot;
    if(this.libraryRoot){
      for(const node of [...root.children]) if(node!==this.inspector&&node!==this.emptySelection)this.libraryRoot.append(node);
      this.libraryRoot.addEventListener('click',onClick);
    }
  }
  find(selector){return this.root.querySelector(selector)||this.libraryRoot?.querySelector(selector);}
  project(){return this.options.project();}
  clips(){return (this.project()?.manual?.text_clips||[]).map(c=>({...c,...this.overrides.get(c.id),...this.dragOverrides.get(c.id)}));}
  dirty(){return Boolean(this.pending.size||this.saving||this.importing);}
  render(force=false){
    const p=this.project();
    const previousSelection=this.selected;
    if(this.projectId!==p?.id){clearTimeout(this.timer);this.pending.clear();this.overrides.clear();this.dragOverrides.clear();this.selected=null;this.projectId=p?.id;this.limit=100;force=true;}
    for(const host of [this.root,this.libraryRoot].filter(Boolean))for(const b of host.querySelectorAll('[data-add],[data-import]'))b.disabled=!p?.draft||this.importing||this.options.busy();
    const clip=this.clips().find(c=>c.id===this.selected);
    if(this.selected&&!clip)this.selected=null;
    if(previousSelection&&previousSelection!==this.selected)this.options.selectionRemoved?.(previousSelection);
    this.inspector.hidden=!clip;
    if(this.emptySelection){this.emptySelection.hidden=Boolean(clip);this.emptySelection.textContent=p?.draft?'Select custom text from the list to edit its template and timing.':'Create an edit before adding text and templates.';}
    if(clip) for(const input of this.root.querySelectorAll('[data-text]')) {
      if(force||document.activeElement!==input)input.value=clip[input.dataset.text] ?? (input.dataset.text==='template' ? 'plain' : '');
      input.disabled=this.importing||(this.options.busy()&&!this.saving);
    }
    this.renderTemplates(clip?.template||'plain');
    this.find('.text-recovery').hidden=!this.pending.size;
    this.find('.text-search').hidden = !this.clips().length;
    this.renderList();
  }
  renderTemplates(template){
    this.showTemplateFields(template);
    if(!this.templatePicker)return;
    const selected=TEXT_TEMPLATES.find(item=>item.id===template)||TEXT_TEMPLATES[0];
    for(const button of this.templatePicker.querySelectorAll('[data-template-choice]')){
      const checked=button.dataset.templateChoice===selected.id;
      button.setAttribute('aria-checked',String(checked));button.tabIndex=checked?0:-1;
      // Our automatic save can briefly mark the app busy. Keep its existing
      // controls focusable while later choices queue behind that same save.
      button.disabled=!this.project()?.draft||!this.selected||this.importing||(this.options.busy()&&!this.saving);
    }
    this.templateDescription.textContent=selected.detail;
  }
  chooseTemplate(template){
    if(!TEXT_TEMPLATES.some(item=>item.id===template)||!this.project()?.draft||this.importing||(this.options.busy()&&!this.saving))return false;
    const clip=this.clips().find(item=>item.id===this.selected);if(!clip)return false;
    if((clip.template||'plain')!==template)this.queueClip(clip.id,{template});
    const select=this.root.querySelector('[data-text=template]');if(select)select.value=template;
    this.renderTemplates(template);return true;
  }
  templateKeydown(event){
    if(event.altKey||event.ctrlKey||event.metaKey)return;
    const steps={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1};
    if(!(event.key in steps)&&!['Home','End'].includes(event.key))return;
    const buttons=[...this.templatePicker.querySelectorAll('[data-template-choice]')].filter(button=>!button.disabled);
    const index=buttons.indexOf(event.target.closest('[data-template-choice]'));if(index<0||!buttons.length)return;
    event.preventDefault();
    const rtl=document.documentElement.dir==='rtl'&&['ArrowLeft','ArrowRight'].includes(event.key)?-1:1;
    const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+steps[event.key]*rtl+buttons.length)%buttons.length;
    if(this.chooseTemplate(buttons[next].dataset.templateChoice))buttons[next].focus();
  }
  // Lower thirds and chapter cards have a second line; they and callouts have a fixed place.
  showTemplateFields(template){
    for(const field of this.root.querySelectorAll('[data-template-field]'))
      field.hidden=field.dataset.templateField==='subtext' ? !['lower_third','chapter'].includes(template) : ['lower_third','callout','chapter'].includes(template);
  }
  renderList(){
    const list=this.find('.text-clip-list'), query=this.find('[data-search]').value.trim().toLocaleLowerCase();
    const clips=this.clips().filter(c=>c.text.toLocaleLowerCase().includes(query)).sort((a,b)=>a.start-b.start);
    list.replaceChildren();
    if(!clips.length){const empty=document.createElement('p');empty.className='text-list-empty';empty.textContent=query?'No custom text matches your search.':'No custom text yet. Add text or a caption to choose a template.';list.append(empty);}
    for(const clip of clips.slice(0,this.limit)) {
      const button=document.createElement('button');button.type='button';button.dataset.textId=clip.id;button.setAttribute('aria-pressed',String(clip.id===this.selected));
      const label=document.createElement('span');label.textContent=clip.text;label.dir='auto';
      const kind={lower_third:'Lower third',chapter:'Chapter',callout:'Callout',highlight:'Highlight'}[clip.template]||(clip.kind==='title'?'Text':'Caption');
      const time=document.createElement('small');time.textContent=`${kind} · ${clip.start.toFixed(2)}–${clip.end.toFixed(2)}s`;
      button.append(label,time);list.append(button);
    }
    this.find('[data-more]').hidden=clips.length<=this.limit;
  }
  async select(id,seek=false){
    if(this.selected!==id && !(await this.flush()))return false;
    this.selected=id;this.render(true);this.options.selected?.(id);
    const clip=this.clips().find(c=>c.id===id);if(seek&&clip)this.options.seek(clip.start);
    return true;
  }
  queueClip(id,patch){
    this.overrides.set(id,{...this.overrides.get(id),...patch});this.pending.set(id,{...this.pending.get(id),...patch});
    this.dragOverrides.delete(id);this.options.preview();this.renderList();this.find('.text-recovery').hidden=false;
    this.status.textContent='Unsaved changes…';clearTimeout(this.timer);this.timer=setTimeout(()=>void this.flush(),500);
  }
  previewClip(id,patch){if(patch)this.dragOverrides.set(id,patch);else this.dragOverrides.delete(id);this.options.preview();}
  async flush(){
    clearTimeout(this.timer);
    if(this.importing)return false;
    if(this.saving){const ok=await this.saving;return ok ? this.flush():false;}
    if(!this.pending.size)return true;
    const p=this.project(), projectId=p?.id;
    if(this.options.busy()){this.status.textContent='Finish the active process, then retry saving text.';return false;}
    const save=async()=>{
      while(this.pending.size && this.project()?.id===projectId){
        const [id,patch]=this.pending.entries().next().value;
        const clip=this.clips().find(c=>c.id===id);
        if(!clip||!clip.text.trim()||!Number.isFinite(clip.start)||!Number.isFinite(clip.end)||clip.start<0||clip.end-clip.start<.08-1e-9||clip.end>this.options.duration()+1e-9||!Number.isInteger(clip.scale)||clip.scale<75||clip.scale>150){
          this.status.textContent='Enter text, valid start/end times within the edit, and a size from 75 to 150. Nothing was saved.';return false;
        }
        let result;
        try{result=await this.options.edit('text_update',{clip_id:id,...patch});}catch(error){this.status.textContent=error.message;return false;}
        if(!result){this.status.textContent='Text was not saved. Retry or discard these changes before leaving.';return false;}
        if(this.project()?.id!==projectId)return false;
        if(this.pending.get(id)===patch){this.pending.delete(id);this.overrides.delete(id);}
      }
      this.status.textContent='Saved';return true;
    };
    this.saving=save();
    try{return await this.saving;}finally{this.saving=null;this.render();this.options.preview();}
  }
  async action(action,detail){
    const projectId=this.project()?.id;if(!projectId||this.options.busy()||!(await this.flush()))return null;
    if(this.project()?.id!==projectId)return null;
    const result=await this.options.edit(action,detail);
    if(result&&this.project()?.id===projectId){this.render(true);this.status.textContent='Saved';this.options.preview();}
    return result;
  }
  async add(kind){
    const duration=this.options.duration();if(duration<.08)return;
    const start=Math.max(0,Math.min(this.options.time(),duration-.08));
    const result=await this.action('text_add',{kind,start,end:Math.min(duration,start+3),text:kind==='title'?'Your title':'Your caption'});
    if(result&&this.project()?.id===result.id){await this.select(result.manual.text_clips.at(-1).id,true);this.root.querySelector('[data-text=text]').focus();}
  }
  async importFile(file){
    const projectId=this.project()?.id;if(!projectId||this.options.busy()||this.importing||!(await this.flush()))return;
    if(file.size>1024*1024){this.status.textContent='Choose an SRT or VTT file smaller than 1 MB.';return;}
    const format=file.name.split('.').at(-1).toLowerCase();if(!['srt','vtt'].includes(format)){this.status.textContent='Choose an .srt or .vtt file.';return;}
    const replace=this.find('[data-replace]').checked;
    this.importing=true;this.render();this.status.textContent='Reading caption file…';
    try{
      const content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
      if(this.project()?.id!==projectId)return;
      const result=await this.options.edit('text_import',{format,content,replace});
      if(this.project()?.id===projectId){this.status.textContent=result ? 'Captions imported. Check their timing in the edited video. Undo reverses this import.' : 'Import failed. Existing captions were not replaced.';}
    }catch(error){if(this.project()?.id===projectId)this.status.textContent=`Could not import: ${error.message}. Save the file as UTF-8 SRT or VTT.`;}
    finally{this.importing=false;this.render(true);this.options.preview();}
  }
  sync(time,sourceMode=false){
    const p=this.project(),visible=!sourceMode&&p?.draft, clips=visible?this.clips().filter(c=>c.start<=time&&time<c.end):[];
    this.layer.hidden=!clips.length;
    const [w,h]=this.options.dimensions();
    const signature=JSON.stringify([clips,w,h,this.stage.clientHeight]);
    if(signature===this.signature)return;this.signature=signature;
    this.layer.replaceChildren();if(!clips.length)return;
    const previewHeight=this.stage.getBoundingClientRect().height;
    for(const clip of clips){
      const item=document.createElement('div'),style=textStyle(clip,w,h,previewHeight);item.className='custom-text-cue';item.dataset.position=clip.position;item.dataset.style=clip.style;item.dir='auto';
      item.dataset.template=clip.template||'plain';
      const main=document.createElement('span');main.className='custom-text-main';main.textContent=clip.text;
      if(clip.subtext&&['lower_third','chapter'].includes(clip.template)){
        const sub=document.createElement('span');sub.className='custom-text-sub';sub.textContent=clip.subtext;
        if(clip.template==='chapter')item.append(sub,main);else item.append(main,sub);
      } else item.append(main);
      if(clip.template==='callout')item.prepend(Object.assign(document.createElement('span'),{className:'custom-text-accent',textContent:'\u258c '}));
      item.style.fontSize=`${style.font}px`;item.style.left=`${style.horizontal}%`;item.style.right=`${style.horizontal}%`;
      item.style.setProperty('--text-stroke',`${style.stroke}px`);item.style.setProperty('--text-margin',`${style.margin}px`);item.style.setProperty('--text-box',`${style.box}px`);this.layer.append(item);
    }
  }
}
