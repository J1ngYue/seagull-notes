// Keep state changes synchronous inside one visual transition.
let readerTransition=null,readerTransitionRevision=0,readerTransitionUpdating=false;
const readerReveals=new WeakMap();
document.addEventListener('pointerdown',()=>readerTransition?.skipTransition(),{capture:true});
function revealReader(element){
 if(!element?.animate||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 readerReveals.get(element)?.cancel();
 const animation=element.animate([{opacity:.35,transform:'translateY(8px)'},{opacity:1,transform:'none'}],{duration:300,easing:'cubic-bezier(.22,.61,.36,1)'});
 readerReveals.set(element,animation);
}
function runReaderTransition(change){
 if(readerTransitionUpdating){change();return}
 const revision=++readerTransitionRevision;
 readerTransition?.skipTransition();
 if(!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches){
  change();revealReader(document.querySelector('.studio-main')||document.querySelector('.panel:not([hidden])'));return;
 }
 const transition=document.startViewTransition(()=>{
  if(revision!==readerTransitionRevision)return;
  document.documentElement.setAttribute('data-reader-switching','');
  readerTransitionUpdating=true;
  try{change()}finally{readerTransitionUpdating=false}
 });
 readerTransition=transition;
 transition.ready.catch(()=>{});
 const finish=()=>{if(readerTransition===transition){readerTransition=null;document.documentElement.removeAttribute('data-reader-switching')}};
 transition.finished.then(finish,finish);
}

