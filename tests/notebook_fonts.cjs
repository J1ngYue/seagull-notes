// node tests/notebook_fonts.cjs <jsdom module path> <rendered notebook.html>
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM,VirtualConsole}=require(process.argv[2]||'jsdom');
const page=fs.readFileSync(process.argv[3],'utf8');
async function open(preference,url='https://notes.example.invalid/fonts.html',savedStyle){
 const errors=[],console=new VirtualConsole();console.on('jsdomError',error=>{if(!error.message.startsWith('Could not parse CSS stylesheet'))errors.push(error.message)});
 const observedPage=page.replace(/(<body\b[^>]*>)/,'$1<script>window.firstReaderState={style:document.documentElement.dataset.initialStyle,booting:document.documentElement.hasAttribute("data-reader-booting"),visibility:getComputedStyle(document.body).visibility};</script>');
 const dom=new JSDOM(observedPage,{url,runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:console,beforeParse(window){
  window.ResizeObserver=class{observe(){}disconnect(){}};window.IntersectionObserver=class{observe(){}unobserve(){}};
  window.document.fonts=new window.EventTarget();window.document.fonts.ready=Promise.resolve();
  window.matchMedia=()=>({matches:false});window.scrollTo=()=>{};window.HTMLElement.prototype.scrollIntoView=()=>{};
  if(preference!==undefined)window.localStorage.setItem('seagull:reader-font',JSON.stringify(preference));
  if(savedStyle!==undefined)window.localStorage.setItem('seagull:style:'+new URL(url).pathname,JSON.stringify(savedStyle));
 }});
 await new Promise(resolve=>dom.window.addEventListener('load',resolve));return {dom,errors};
}
(async()=>{
 const {dom,errors}=await open();const w=dom.window,d=w.document,font=d.querySelector('#font-select'),style=d.querySelector('#style-select');
 const original=d.querySelector('#markdown .raw').textContent,codes=Array.from(d.querySelectorAll('#notes .code-block code')).map(n=>n.textContent);
 const chapters=Array.from(d.querySelectorAll('.chapter')),panels=Array.from(d.querySelectorAll('.panel[role=tabpanel]'));
 for(const mode of ['paper','atlas','folio','whale','journal','moonlight','pixel']){
  style.value=mode;style.dispatchEvent(new w.Event('change'));
  for(const value of ['sans','serif','kai','hand','default']){
   font.value=value;font.dispatchEvent(new w.Event('change'));
   assert.equal(d.body.dataset.readerFont,value);assert.equal(JSON.parse(w.localStorage.getItem('seagull:reader-font')),value);
   assert.equal(d.querySelector('#markdown .raw').textContent,original);
   assert.deepEqual(Array.from(d.querySelectorAll('#notes .code-block code')).map(n=>n.textContent),codes);
  }
  if(['whale','journal','moonlight','pixel'].includes(mode)){
   const scene=d.querySelector('.reader-scene');assert.equal(scene.getAttribute('aria-label'),{whale:'鲸游·知识海',journal:'日系手账',moonlight:'月光玻璃',pixel:'像素桌面'}[mode]);
   assert.equal(d.body.dataset.readerTemplate,mode);assert.equal(d.querySelectorAll('.reader-scene').length,1);
   assert.deepEqual(Array.from(scene.querySelectorAll('.chapter')),chapters,'Chapter nodes and event bindings must survive template changes');
   if(mode==='pixel'){
    scene.querySelector('[data-studio-action=desktop]').click();assert.equal(scene.dataset.screen,'desktop');assert.equal(scene.querySelector('[data-window=notes]').hidden,true);assert.equal(scene.querySelector('.pixel-file-icons').hidden,true);
    scene.querySelector('.pixel-notes-icon').click();assert.equal(scene.dataset.screen,'shelf');assert.equal(scene.querySelector('[data-window=notes]').hidden,false);assert.equal(scene.querySelector('.pixel-file-icons').hidden,true);
    scene.querySelector('.all-cards .shelf-card').click();assert.equal(scene.dataset.screen,'reading');assert.equal(scene.querySelector('.pixel-file-icons').hidden,false);assert.equal(scene.querySelectorAll('.pixel-file-icons button').length,5);
    scene.querySelector('[data-window-action=close]').click();assert.equal(scene.dataset.screen,'desktop');assert.equal(scene.querySelector('.pixel-file-icons').hidden,true);
   }
   Array.from(scene.querySelectorAll('.toc a')).forEach((link,index)=>{link.click();assert.equal(chapters.filter(c=>!c.hidden).length,chapters.length);assert.equal(chapters[index].hidden,false);assert.equal(w.location.hash,'#'+chapters[index].id)});
   if(mode==='whale'){
    d.dispatchEvent(new w.CustomEvent('seagull:position',{detail:2}));assert.equal(scene.querySelectorAll('.ocean-route .active').length,1);assert.equal(scene.querySelector('.scene-current-title').textContent,chapters[2].querySelector('h2').textContent);
   }else{
    scene.querySelector('[data-studio-action=shelf]').click();assert.equal(scene.dataset.screen,'shelf');
    const input=scene.querySelector('.shelf-search');input.value='no such note xyz';input.dispatchEvent(new w.Event('input'));assert.equal(scene.querySelectorAll('.all-cards .shelf-card:not([hidden])').length,0);assert.equal(scene.querySelector('.shelf-empty').hidden,false);
    input.value='';input.dispatchEvent(new w.Event('input'));assert.ok(scene.querySelectorAll('.all-cards .shelf-card:not([hidden])').length>0);
    scene.querySelector('.outline-chapters button').click();assert.equal(scene.dataset.screen,'reading');assert.equal(w.location.hash,'#'+chapters[0].id);
    if(mode==='pixel'){
     const window=scene.querySelector('[data-window=notes]');scene.querySelector('[data-window-action=minimize]').click();assert.equal(window.hidden,true);scene.querySelector('[data-window-restore=notes]').click();assert.equal(window.hidden,false);
     scene.querySelector('[data-window-action=maximize]').click();assert.equal(window.classList.contains('maximized'),true);scene.querySelector('[data-window-action=maximize]').click();assert.equal(window.classList.contains('maximized'),false);
     assert.equal(scene.querySelectorAll('.pixel-resize-grip').length,16);
     const measure=window.getBoundingClientRect,viewportWidth=w.innerWidth,readingHash=w.location.hash;
     window.getBoundingClientRect=()=>({left:100,top:80,width:parseFloat(window.style.width)||600,height:parseFloat(window.style.height)||480});
     window.querySelector('.pixel-resize-grip[data-resize=e]').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',shiftKey:true,bubbles:true}));
     assert.equal(window.style.width,'640px');assert.equal(window.style.height,'480px');assert.equal(w.location.hash,readingHash);
     w.innerWidth=720;w.dispatchEvent(new w.Event('resize'));assert.equal(window.style.width,'612px');
     w.innerWidth=viewportWidth;window.getBoundingClientRect=measure;
     const fullscreen=scene.querySelector('[data-pixel-fullscreen]');
     Object.defineProperty(d,'fullscreenElement',{configurable:true,value:null,writable:true});
     d.documentElement.requestFullscreen=async()=>{d.fullscreenElement=d.documentElement;d.dispatchEvent(new w.Event('fullscreenchange'))};
     d.exitFullscreen=async()=>{d.fullscreenElement=null;d.dispatchEvent(new w.Event('fullscreenchange'))};
     fullscreen.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(fullscreen.getAttribute('aria-pressed'),'true');assert.equal(fullscreen.getAttribute('aria-label'),'退出全屏');
     d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));await new Promise(resolve=>setImmediate(resolve));assert.equal(fullscreen.getAttribute('aria-pressed'),'false');
     d.documentElement.requestFullscreen=async()=>{throw new Error('Not allowed')};fullscreen.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(scene.querySelector('.pixel-system-message').hidden,false);assert.equal(fullscreen.getAttribute('aria-pressed'),'false');
    }else if(mode==='journal'){
     const poses=['bass','coffee','reading','star','writing'];
     for(const container of [scene.querySelector('.studio-home'),scene.querySelector('.studio-reading')])assert.deepEqual(Array.from(container.querySelectorAll('[data-sticker]')).map(el=>el.dataset.sticker).sort(),poses);
     assert.equal(scene.querySelectorAll('button[data-sticker]').length,0);const sticker=scene.querySelector('[data-sticker]'),pose=sticker.dataset.sticker;sticker.click();assert.equal(sticker.dataset.sticker,pose);
     const month=scene.querySelector('.calendar-title').textContent;scene.querySelector('[data-journal-month="1"]').click();assert.notEqual(scene.querySelector('.calendar-title').textContent,month);scene.querySelector('[data-journal-month="-1"]').click();assert.equal(scene.querySelector('.calendar-title').textContent,month);
     const memo=scene.querySelector('.journal-memo-input');memo.value='记住今天的学习';memo.dispatchEvent(new w.Event('input'));assert.equal(JSON.parse(w.localStorage.getItem('seagull:journal:memo')),memo.value);
    }
   }
   scene.querySelector('[data-scene-action=overview]').click();assert.equal(chapters.every(c=>c.hidden),false);assert.equal(d.querySelector('#notes>.summary').hidden,false);assert.equal(d.querySelector('#notes>.study-widgets').hidden,false);
   scene.querySelector('[data-scene-panel=map]').click();assert.equal(d.body.dataset.view,'map');assert.equal(d.querySelector('#map').hidden,false);
   if(mode!=='whale'){d.querySelector('[data-map-action=expand]').click();assert.equal(d.querySelector('.mindmap-viewer.expanded').parentElement,d.body);d.querySelector('[data-map-action=expand]').click();assert.equal(d.querySelector('.mindmap-viewer').closest('.studio'),scene);}
   scene.querySelector('[data-scene-panel=markdown]').click();assert.equal(d.querySelector('#markdown .raw').textContent,original);
   scene.querySelector('[data-scene-panel=notes]').click();
  }else{
   assert.equal(d.querySelector('.reader-scene'),null);assert.equal(d.body.dataset.readerTemplate,undefined);assert.equal(chapters.every(c=>!c.hidden),true);
  }
  assert.deepEqual(Array.from(d.querySelectorAll('.panel[role=tabpanel]')),panels);
 }
 style.value='paper';style.dispatchEvent(new w.Event('change'));assert.equal(d.querySelector('.reader-scene'),null);assert.equal(chapters.every(c=>!c.hidden),true);
 font.value='serif';font.dispatchEvent(new w.Event('change'));const persisted=JSON.parse(w.localStorage.getItem('seagull:reader-font'));
 assert.deepEqual(errors,[]);dom.window.close();
 for(const [stored,expected] of [[persisted,'serif'],['unknown','default']]){
  const next=await open(stored);assert.equal(next.dom.window.document.querySelector('#font-select').value,expected);assert.equal(next.dom.window.document.body.dataset.readerFont,expected);assert.deepEqual(next.errors,[]);next.dom.window.close();
 }
 const opened=await open(undefined,'https://notes.example.invalid/fonts.html?style=pixel&open=notes');assert.equal(opened.dom.window.document.querySelector('.pixel-studio').dataset.screen,'reading');assert.equal(opened.dom.window.document.querySelector('.pixel-file-icons').hidden,false);assert.deepEqual(opened.errors,[]);opened.dom.window.close();
 for(const [query,stored,expected] of [['journal','paper','journal'],['moonlight','paper','moonlight'],['pixel','paper','pixel'],['','journal','journal'],['anime',undefined,'journal'],['cyber',undefined,'moonlight']]){
  const initial=await open(undefined,'https://notes.example.invalid/fonts.html'+(query?'?style='+query:''),stored),document=initial.dom.window.document;
  assert.deepEqual({...initial.dom.window.firstReaderState},{style:expected,booting:true,visibility:'hidden'},'Authored content must stay hidden before the requested reader mounts');
  assert.equal(document.body.dataset.style,expected);assert.equal(document.documentElement.hasAttribute('data-reader-booting'),false);assert.equal(initial.dom.window.getComputedStyle(document.body).visibility,'visible');assert.deepEqual(initial.errors,[]);initial.dom.window.close();
 }
 const changed=await open(undefined,'https://notes.example.invalid/fonts.html?style=journal'),picker=changed.dom.window.document.querySelector('#style-select');picker.value='moonlight';picker.dispatchEvent(new changed.dom.window.Event('change'));assert.equal(new URL(changed.dom.window.location.href).searchParams.get('style'),'moonlight');assert.equal(changed.dom.window.document.body.dataset.style,'moonlight');assert.deepEqual(changed.errors,[]);changed.dom.window.close();
 process.stdout.write('Seven styles, five fixed stickers on each journal screen, full content, shelf navigation and pre-paint theme selection verified.\n');
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1});
