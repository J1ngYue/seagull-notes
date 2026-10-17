// node tests/reader_motion.cjs <jsdom module path>
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.argv[2]||'jsdom');
const source=fs.readFileSync('skill/assets/reader-motion.js','utf8');
(async()=>{
 const dom=new JSDOM('<main class="studio-main"></main>',{runScripts:'outside-only'}),w=dom.window,calls=[];let reduced=false,value='initial';
 w.matchMedia=()=>({matches:reduced});w.eval(source);
 w.document.startViewTransition=update=>{let finish;const transition={update,ready:Promise.resolve(),finished:new Promise(resolve=>finish=resolve),skipTransition(){this.skipped=true},finish:()=>finish()};calls.push(transition);return transition};
 w.runReaderTransition(()=>value='obsolete');w.runReaderTransition(()=>value='latest');
 assert.equal(calls[0].skipped,true);assert.equal(calls[0].update(),undefined);assert.equal(value,'initial');
 assert.equal(calls[1].update(),undefined,'The snapshot callback must not wait on an animation frame while rendering is suppressed');assert.equal(value,'latest');assert.equal(w.document.documentElement.hasAttribute('data-reader-switching'),true);
 calls[1].finish();await new Promise(setImmediate);assert.equal(w.document.documentElement.hasAttribute('data-reader-switching'),false);
 w.runReaderTransition(()=>w.runReaderTransition(()=>value='nested'));const count=calls.length;calls.at(-1).update();assert.equal(value,'nested');assert.equal(calls.length,count);calls.at(-1).finish();await new Promise(setImmediate);
 reduced=true;w.runReaderTransition(()=>value='reduced');assert.equal(value,'reduced');assert.equal(calls.length,count);
 delete w.document.startViewTransition;reduced=false;w.runReaderTransition(()=>value='fallback');assert.equal(value,'fallback');
 dom.window.close();console.log('Latest navigation wins; nested changes are atomic; snapshot callbacks do not block painting; reduced motion and fallback preserve actions.');
})().catch(error=>{console.error(error);process.exitCode=1});
