// Explicit user controls. The server owns parsing, conflicts and enforcement.
// No language-model call, automatic rewrite or claim of editorial approval.
let activeReview = null;

export function requestReviewSettings(base, fields) {
  return {...base, output_count:Number(fields.output_count.value),
    target_duration:Number(fields.target_duration.value), duration_mode:fields.duration_mode.value,
    aspect:fields.aspect.value, source_continuity:fields.source_continuity.value,
    edit_style:fields.edit_style.value, instruction:fields.instruction.value};
}

export function reviewEditingRequest({settings, styles=[], projectId, revision, check, isCurrent}) {
  if(activeReview)return Promise.resolve(null);
  return new Promise(resolve=>{
    const make=(tag,text)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;return e;};
    const dialog=make('dialog');dialog.className='editing-request-review';activeReview=dialog;
    dialog.setAttribute('aria-labelledby','editingRequestTitle');
    const title=make('h2','Review your editing request');title.id='editingRequestTitle';
    const note=make('p','One finished main edit per generation. One output may contain several cuts. Only a continuous-source request forbids internal cuts. Style is a preference; explicit instructions remain authoritative.');
    const form=make('form'),fields={},grid=make('div');grid.className='request-review-grid';
    function field(key,label,choices,value){
      const row=make('label',label),e=make(choices?'select':key==='instruction'?'textarea':'input');
      e.dataset.requestField=key;
      if(choices)for(const [id,name]of choices){const option=make('option',name);option.value=id;e.append(option);}
      else if(key==='instruction'){e.rows=4;e.maxLength=8000;e.dir='auto';}
      else{e.type='number';e.required=true;e.min=key==='output_count'?'1':'8';e.max=key==='output_count'?'10':'86400';e.step=key==='output_count'?'1':'.01';}
      e.value=String(value??'');fields[key]=e;row.append(e);grid.append(row);return e;
    }
    field('output_count','Finished outputs (currently 1 supported)',null,settings.output_count??1);
    field('target_duration','Configured length (seconds)',null,settings.target_duration??60);
    field('duration_mode','Length intent',[['target','Aim for configured length'],['style','Maximum / style may finish earlier']],settings.duration_mode||'target');
    if(settings.goal!=='short'){
      fields.target_duration.disabled=true;fields.duration_mode.disabled=true;
      grid.append(make('p','This mode edits the whole recording. Highlight length controls apply to Short/Reel mode; explicit unsupported lengths will be blocked.'));
    }
    field('aspect','Output aspect ratio',[['9:16','9:16 portrait'],['16:9','16:9 landscape'],['1:1','1:1 square'],['4:5','4:5 portrait'],['source','Original aspect']],settings.aspect||'9:16');
    field('source_continuity','Source arrangement',[['unspecified','Follow written request; cuts allowed by default'],['required','One continuous source range — no internal cuts'],['cuts_allowed','Cuts / montage permitted within one output']],settings.source_continuity||'unspecified');
    const styleRows=styles.map(s=>[s.id,typeof s.name==='string'?s.name:s.name?.en||s.id]);
    if(!styleRows.some(r=>r[0]===settings.edit_style))styleRows.unshift([settings.edit_style||'smart',settings.edit_style||'CUTROOM Smart']);
    field('edit_style','Visual / editing style (preference)',styleRows,settings.edit_style||'smart');
    const instruction=field('instruction','Content goal and hard instructions — Hebrew / English',null,settings.instruction||'');instruction.parentElement?.classList?.add('request-review-instruction');
    const caveat=make('p','Keep exact or ranged lengths in the written request (for example: “Aim for 45–60 seconds”). Unrecognized wording, content accuracy and editorial quality remain unverified. A passed request check does not prove a good edit.');
    const result=make('p','Checking request…');result.className='request-review-result';result.dir='auto';result.setAttribute('role','status');
    const checkButton=make('button','Check request');checkButton.type='button';checkButton.dataset.requestCheck='true';
    const keep=make('button','Keep current edit');keep.type='button';keep.dataset.requestKeep='true';
    const generate=make('button','Generate reviewed request');generate.type='submit';generate.disabled=true;generate.dataset.requestGenerate='true';
    const actions=make('div');actions.className='request-review-actions';actions.append(keep,checkButton,generate);
    let checked=null,checking=false,settled=false;
    const invalidate=()=>{checked=null;generate.disabled=true;result.textContent='Request changed. Check it before generation.';};
    for(const e of Object.values(fields)){e.addEventListener('input',invalidate);e.addEventListener('change',invalidate);}
    const current=()=>isCurrent()&&activeReview===dialog&&!settled;
    const validate=async()=>{
      if(checking||!form.reportValidity())return;
      if(!current()){invalidate();result.textContent='The project or its settings changed. Close this review and reopen it; the current edit was kept.';return;}
      checking=true;checkButton.disabled=true;generate.disabled=true;
      const requested=requestReviewSettings(settings,fields),identity=JSON.stringify(requested);
      try{
        const response=await check(requested);
        if(!current()||response.project_id!==projectId||response.revision!==revision){invalidate();result.textContent='The project changed. Close and review the current version; nothing was generated.';return;}
        if(JSON.stringify(requestReviewSettings(settings,fields))!==identity){invalidate();return;}
        const issues=response.contract?.issues||[];
        if(!response.ready||issues.length){checked=null;result.textContent=issues.map(x=>x.reason).join('\n')||'This request is not supported.';return;}
        const b=response.duration_bounds,c=response.contract.selection_controls||{};
        const arrangement=c.source_continuity==='required'?'continuous source; no internal cuts':c.related_source_cuts_allowed?'cuts permitted within one output':'no explicit continuity constraint';
        const length=b?`${b.minimum_seconds.toFixed(2)}–${b.maximum_seconds.toFixed(2)} seconds (${b.origin})`:'whole-recording edit; highlight length is not applied';
        result.textContent=`1 main output · ${requested.aspect} · ${length}\n${arrangement}\nStyle preference: ${requested.edit_style}. Written content requirements and quality remain unverified.`;
        checked={settings:requested,identity};generate.disabled=false;
      }catch(error){checked=null;result.textContent=error.message||'Request check failed. The current edit was kept.';}
      finally{checking=false;checkButton.disabled=false;}
    };
    const finish=value=>{if(settled)return;settled=true;resolve(value);if(dialog.open)dialog.close();else dialog.remove();if(activeReview===dialog)activeReview=null;};
    checkButton.addEventListener('click',validate);keep.addEventListener('click',()=>finish(null));
    form.addEventListener('submit',event=>{
      event.preventDefault();if(!form.reportValidity())return;
      if(!current()||!checked||JSON.stringify(requestReviewSettings(settings,fields))!==checked.identity){invalidate();result.textContent='Review is stale or changed. Check the current request again.';return;}
      finish(checked.settings);
    });
    dialog.addEventListener('cancel',()=>finish(null));dialog.addEventListener('close',()=>{finish(null);dialog.remove();});
    form.append(grid,caveat,result,actions);dialog.append(title,note,form);document.body.append(dialog);dialog.showModal();
    validate();
  });
}
