// node tests/notebook_fonts.cjs <jsdom module path> <rendered notebook.html>
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM,VirtualConsole}=require(process.argv[2]||'jsdom');
const page=fs.readFileSync(process.argv[3],'utf8');
async function open(preference){
 const errors=[],console=new VirtualConsole();console.on('jsdomError',error=>{if(!error.message.startsWith('Could not parse CSS stylesheet'))errors.push(error.message)});
 const dom=new JSDOM(page,{url:'https://notes.example.invalid/fonts.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:console,beforeParse(window){
  window.ResizeObserver=class{observe(){}};window.IntersectionObserver=class{observe(){}unobserve(){}};
  window.document.fonts=new window.EventTarget();window.document.fonts.ready=Promise.resolve();
  window.matchMedia=()=>({matches:false});window.scrollTo=()=>{};window.HTMLElement.prototype.scrollIntoView=()=>{};
  if(preference!==undefined)window.localStorage.setItem('seagull:reader-font',JSON.stringify(preference));
 }});
 await new Promise(resolve=>dom.window.addEventListener('load',resolve));return {dom,errors};
}
(async()=>{
 const {dom,errors}=await open();const w=dom.window,d=w.document,font=d.querySelector('#font-select'),style=d.querySelector('#style-select');
 const original=d.querySelector('#markdown .raw').textContent,codes=Array.from(d.querySelectorAll('#notes .code-block code')).map(n=>n.textContent);
 const chapters=Array.from(d.querySelectorAll('.chapter')),panels=Array.from(d.querySelectorAll('.panel[role=tabpanel]'));
 for(const mode of ['paper','atlas','folio','whale','anime','cyber']){
  style.value=mode;style.dispatchEvent(new w.Event('change'));
  for(const value of ['sans','serif','kai','hand','default']){
   font.value=value;font.dispatchEvent(new w.Event('change'));
   assert.equal(d.body.dataset.readerFont,value);assert.equal(JSON.parse(w.localStorage.getItem('seagull:reader-font')),value);
   assert.equal(d.querySelector('#markdown .raw').textContent,original);
   assert.deepEqual(Array.from(d.querySelectorAll('#notes .code-block code')).map(n=>n.textContent),codes);
  }
  if(['whale','anime','cyber'].includes(mode)){
   const scene=d.querySelector('.reader-scene');assert.equal(scene.getAttribute('aria-label'),{whale:'肥鱼自习室',anime:'次元放映厅',cyber:'霓虹矩阵浅色知识工作台'}[mode]);
   assert.equal(d.body.dataset.readerTemplate,mode);assert.equal(d.querySelectorAll('.reader-scene').length,1);
   assert.deepEqual(Array.from(scene.querySelectorAll('.chapter')),chapters,'Chapter nodes and event bindings must survive template changes');
   Array.from(scene.querySelectorAll('.toc a')).forEach((link,index)=>{link.click();assert.equal(chapters.filter(c=>!c.hidden).length,1);assert.equal(chapters[index].hidden,false);assert.equal(w.location.hash,'#'+chapters[index].id)});
   assert.equal(scene.querySelector('[data-scene-action=next]').disabled,true);
   scene.querySelector('[data-scene-action=overview]').click();assert.equal(chapters.every(c=>c.hidden),true);assert.equal(d.querySelector('#notes>.summary').hidden,false);assert.equal(d.querySelector('#notes>.study-widgets').hidden,false);
   scene.querySelector('[data-scene-action=map]').click();assert.equal(d.body.dataset.view,'map');assert.equal(d.querySelector('#map').hidden,false);
   d.querySelector('#tab-markdown').click();assert.equal(d.querySelector('#markdown .raw').textContent,original);
   d.querySelector('#tab-notes').click();
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
 process.stdout.write('Six styles, five fonts, independent shells, every chapter, overview/review and format switches preserve original content nodes.\n');
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1});
