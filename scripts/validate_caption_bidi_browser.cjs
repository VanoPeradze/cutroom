/* Offline real-browser companion to test_caption_bidi_render.py.
 * Uses the production rendering functions and styles with synthetic captions.
 * Requires an existing Playwright/Chromium installation, never downloads one.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web/app.js'), 'utf8');
function functionSource(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing production function ${name}`);
  const next = app.indexOf('\nfunction ', start + 1);
  // The trailing comments/constants after updatePreviewCaption are harmless,
  // but keeping just the function avoids redeclaring production constants.
  return app.slice(start, next).slice(0, app.slice(start, next).lastIndexOf('\n}') + 2);
}
const functions = ['renderCaptionItemPreview', 'updatePreviewCaption'].map(functionSource).join('\n');
const rtl = app.match(/const RTL_CHARACTERS = (.+);/)[1];
const styles = fs.readFileSync(path.join(root, 'web/styles.css'), 'utf8');
const authoredOnly = process.argv.includes('--authored-only');
const output = authoredOnly ? null : path.resolve(process.argv[2] || path.join(root, 'validation-work/caption-bidi-browser'));
if (output) fs.mkdirSync(output, { recursive: true });

// --authored-only runs actual TextStudio preview layout offline and writes no file.
async function validateAuthored(browser) {
  const page = await browser.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => route.abort());
  await page.setContent('<aside id="tools" hidden></aside><div id="stage" style="position:relative"></div>');
  await page.addStyleTag({content:fs.readFileSync(path.join(root,'web/text-studio.css'),'utf8')});
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'web/text-studio.js'),'utf8').replace(/^export /gm,'')+'\nwindow.AuthoredStudio=TextStudio;'});
  const count = await page.evaluate(() => {
    const stage=document.querySelector('#stage'), p={id:'qa',draft:{},manual:{text_clips:[]}};
    let size, checked=0;
    const studio=new window.AuthoredStudio(document.querySelector('#tools'),stage,{
      project:()=>p,busy:()=>false,dimensions:()=>size,preview:()=>{},time:()=>1,
      edit:()=>{throw Error('Layout must not edit the project');}
    });
    const he='מצלמים ב 4K 60fps היום.', en='Filmed in 4K today.';
    const fail=(msg)=>{throw Error(msg);};
    function x(span,offset) {
      const range=document.createRange();range.setStart(span.firstChild,offset);range.setEnd(span.firstChild,offset+1);
      const box=range.getBoundingClientRect();if(!box.width)fail('Missing rendered glyph');
      return box.left;
    }
    function line(span,start,text) {
      const dot=x(span,start+text.length-1), first=x(span,start);
      if(text===en ? dot<=first : dot>=first)fail('Misplaced '+text+' under '+span.parentElement.dataset.template);
      if(text===he && x(span,start+text.indexOf('4K'))>=x(span,start+text.indexOf('60fps')))fail('Reversed Latin phrase');
    }
    for(const dims of [[960,540],[390,844]])for(const dir of ['ltr','rtl']){
      size=dims;stage.style.width=dims[0]+'px';stage.style.height=dims[1]+'px';document.documentElement.dir=dir;
      for(const template of ['plain','chapter','lower_third','highlight','callout'])for(const [a,b] of [[he,en],[en,he]]){
        for(const separate of ['chapter','lower_third'].includes(template)?[false,true]:[false]){
          const text=separate?a:a+'\n'+b, row={id:'text_qa',kind:'title',template,position:'center',style:'clean',scale:75,start:0,end:2,text,...(separate?{subtext:b}:{})};
          p.manual.text_clips=[row];const before=JSON.stringify(p);studio.sync(1);
          const main=stage.querySelector('.custom-text-main'),sub=stage.querySelector('.custom-text-sub');
          if(main.textContent!==text || (separate&&sub.textContent!==b))fail('Authored text changed');
          line(main,0,a);line(separate?sub:main,separate?0:a.length+1,b);
          if(template==='callout' && stage.querySelector('.custom-text-accent')?.textContent.trim()!=='▌')fail('Callout accent lost');
          if(JSON.stringify(p)!==before)fail('Project was mutated');checked++;
        }
      }
    }
    return checked;
  });
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:count,browser:browser.version(),case:'authored preview paragraph order',filesWritten:0}));
}
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CUTROOM_CHROMIUM_EXECUTABLE ? { executablePath: process.env.CUTROOM_CHROMIUM_EXECUTABLE } : {}) });
  try {
  if (authoredOnly) { await validateAuthored(browser); return; }
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({status:'running'})+'\n');
  const page = await browser.newPage({ viewport: { width: 1400, height: 1500 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // No media, provider, telemetry, remote font or other request is permitted.
  await page.route('**/*', route => route.abort());
  await page.setContent('<div class="preview-stage" id="stage"><div class="preview-caption" id="previewCaption" dir="auto"></div></div>');
  await page.addStyleTag({ content: styles });
  await page.addStyleTag({ content: '#stage {position:relative; background:#111; margin:0; max-width:none; aspect-ratio:auto;} body {margin:0;} .preview-caption {font-family:Arial,sans-serif;}' });
  await page.addScriptTag({ content: `
    let fixture;
    const state = {project: {}, captionSelection: null};
    const elements = {previewCaption:document.querySelector('#previewCaption')};
    const RTL_CHARACTERS = ${rtl};
    const HIGHLIGHT_WORDS_PER_CAPTION = 4;
    function captionSettingsFromControls() {return {style:fixture.style,position:'auto',scale:100,words:9};}
    function captionItems() {return [{id:'synthetic',start:0,end:2,estimated_words:false}];}
    function captionItemLine() {return {text:fixture.text,words:fixture.text.split(' ').map((w,i)=>[i/10,(i+1)/10,w])};}
    function cameraAt() {return 'A';}
    function playbackProject() {return {analysis:{transcript:{segments:[{start:0,end:2,text:fixture.text}]}}};}
    function captionBurnEnabled() {return true;}
    function previewUsesSourceTime() {return true;}
    function previewUsesIndependentTracks() {return false;}
    function captionPreviewText(segment) {return segment.text;}
    function captionActiveWord() {return 1;}
    ${functions}
    window.runCaptionFixture = (input) => {
      fixture=input;
      const stage=document.querySelector('#stage');
      stage.dataset.aspect=input.width<input.height?'9:16':'16:9';
      stage.style.width=input.width+'px';stage.style.height=input.height+'px';
      if(input.route==='item')renderCaptionItemPreview(.15);else updatePreviewCaption(.15);
      const el=elements.previewCaption;
      function tokenRect(token) {
        const offset=el.textContent.indexOf(token);if(offset<0)throw Error('Missing token '+token);
        const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),range=document.createRange();
        let consumed=0,node,start=false;
        while(node=walker.nextNode()) {
          if(!start&&offset<consumed+node.length){range.setStart(node,offset-consumed);start=true;}
          if(start&&offset+token.length<=consumed+node.length){range.setEnd(node,offset+token.length-consumed);break;}
          consumed+=node.length;
        }
        const r=range.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
      }
      return {text:el.textContent,hidden:el.hidden,highlight:el.querySelectorAll('.caption-active-word').length,
        tokens:input.tokens.map(token=>({token,...tokenRect(token)})),style:el.dataset.captionStyle,
        rect:(()=>{let r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};})()};
    };` });
  const results=[];
  const phrases = [ ['4K 60fps',['4K','60fps']], ['Sony A7 IV',['Sony','A7','IV']], ['Sony A7 IV / H.264',['Sony','A7','IV','H.264']], ['Sony, Canon',['Sony','Canon']], ['Sony (A7 IV)',['Sony','A7','IV']], ['H.264',['H.264']], ['S-Log3',['S-Log3']], ['4K/60fps',['4K','60fps']], ['(4K)',['4K']], ['Swit',['Swit']] ];
  for (const route of ['item','source']) for (const style of ['clean','bold','boxed','highlight']) for(const [width,height] of [[1280,720],[720,1280],[240,426]]) for(const [phrase,tokens] of phrases) {
    const text=`מצלמים ב ${phrase} היום.`;
    const result=await page.evaluate(input=>window.runCaptionFixture(input),{route,style,width,height,text,tokens});
    assert.equal(result.text,text,'Preview must preserve original logical text');
    assert.equal(result.hidden,false);assert.equal(result.style,style);assert.equal(result.highlight,0,'RTL highlights must match plain export policy');
    for(let i=1;i<result.tokens.length;i++) {
      const a=result.tokens[i-1],b=result.tokens[i];
      assert.ok(b.y>a.y+2 || (Math.abs(b.y-a.y)<2 && b.x>a.x),`${route}/${style}/${width}: wrong Latin token order ${phrase}: ${JSON.stringify(result.tokens)}`);
    }
    assert.ok(result.rect.x>=0 && result.rect.x+result.rect.width<=width+1,'Caption box outside stage');
    results.push({route,style,width,height,phrase,verified:'logical-text, Latin visual order, RTL-highlight policy, horizontal bounds'});
  }
  // Explicit newlines and paragraph direction, including a pure-LTR first row.
  for(const route of ['item','source']) for(const style of ['clean','bold','boxed','highlight']) {
    const text='מצלמים ב 4K 60fps היום.\nEnglish Sony A7 IV';
    const result=await page.evaluate(input=>window.runCaptionFixture(input),{route,style,width:720,height:1280,text,tokens:['4K','60fps','Sony','A7','IV']});
    assert.equal(result.text,text);assert.equal(result.highlight,0);
    assert.ok(result.tokens[0].x<result.tokens[1].x);
    assert.ok(result.tokens[2].x<result.tokens[3].x && result.tokens[3].x<result.tokens[4].x);
    assert.ok(result.tokens[2].y>result.tokens[0].y+2, 'Authored newline must render as a separate physical line, matching ASS');
    results.push({route,style,case:'explicit multiline',verified:'text and intra-phrase visual order'});
  }
  // Active-word spans stay functional in LTR, not disabled to make RTL pass.
  for(const route of ['item','source']) {
    const result=await page.evaluate(input=>window.runCaptionFixture(input),{route,style:'highlight',width:720,height:1280,text:'Shoot 4K 60fps today.',tokens:['4K','60fps']});
    assert.equal(result.highlight,1);assert.ok(result.tokens[0].x<result.tokens[1].x);
    results.push({route,case:'LTR active-word span',verified:true});
  }
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(output,'ltr-highlight-control.png')});
  await page.evaluate(input=>window.runCaptionFixture(input),{route:'item',style:'highlight',width:720,height:1280,text:'מצלמים ב Sony A7 IV / H.264 היום.',tokens:['Sony','A7','IV','H.264']});
  await page.screenshot({path:path.join(output,'hebrew-portrait.png')});
  const report={status:'passed',passed:results.length,browser:browser.version(),sourceSha256:{app:crypto.createHash('sha256').update(app).digest('hex'),styles:crypto.createHash('sha256').update(styles).digest('hex')},scope:'Synthetic production renderer functions and production CSS, offline Chromium; not a whole-app user-media test or pixel-identical browser/FFmpeg typography.',results};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:report.passed,browser:report.browser,output}));
  } catch(error) {
    if (output) fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({status:'failed',error:String(error)},null,2)+'\n');
    throw error;
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
