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
 for(const mode of ['paper','atlas','folio']){
  style.value=mode;style.dispatchEvent(new w.Event('change'));
  for(const value of ['sans','serif','kai','hand','default']){
   font.value=value;font.dispatchEvent(new w.Event('change'));
   assert.equal(d.body.dataset.readerFont,value);assert.equal(JSON.parse(w.localStorage.getItem('seagull:reader-font')),value);
   assert.equal(d.querySelector('#markdown .raw').textContent,original);
   assert.deepEqual(Array.from(d.querySelectorAll('#notes .code-block code')).map(n=>n.textContent),codes);
  }
 }
 font.value='serif';font.dispatchEvent(new w.Event('change'));const persisted=JSON.parse(w.localStorage.getItem('seagull:reader-font'));
 assert.deepEqual(errors,[]);dom.window.close();
 for(const [stored,expected] of [[persisted,'serif'],['unknown','default']]){
  const next=await open(stored);assert.equal(next.dom.window.document.querySelector('#font-select').value,expected);assert.equal(next.dom.window.document.body.dataset.readerFont,expected);assert.deepEqual(next.errors,[]);next.dom.window.close();
 }
 process.stdout.write('Five font choices work across three styles; preference reloads and source/code remain exact.\n');
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1});
