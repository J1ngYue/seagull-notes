// Independent shells share the original content nodes and their existing event bindings.
const themedModes=['whale','anime','cyber'];
const sceneNodes={heading:document.querySelector('.note-head'),index:document.querySelector('.sidebar'),formats:document.querySelector('.tabs'),panels:Array.from(document.querySelectorAll('.panel[role=tabpanel]'))};
const sceneHomes=new Map();[sceneNodes.heading,sceneNodes.index,sceneNodes.formats,...sceneNodes.panels].forEach(node=>{const marker=document.createComment('reader node home');node.before(marker);sceneHomes.set(node,marker)});
let readerScene=null,sceneIndex=-1,sceneExtras=[],sceneExtraVisibility=new Map(),sceneMessage=0;
function unmountThemeScene(){
 if(!readerScene)return;
 sceneHomes.forEach((marker,node)=>marker.after(node));chapters.forEach(chapter=>{chapter.hidden=false});sceneExtraVisibility.forEach((hidden,node)=>{node.hidden=hidden});
 readerScene.remove();readerScene=null;sceneExtras=[];sceneExtraVisibility.clear();delete document.body.dataset.readerTemplate;
}
function getThemeReadingChapter(){return Math.max(0,sceneIndex)}
function updateThemeMeters(){
 if(!readerScene)return;
 const total=chapters.length,title=sceneIndex<0?'学习概览与复习':chapters[sceneIndex].querySelector('h2').textContent;
 readerScene.querySelectorAll('.scene-position').forEach(node=>{node.textContent=sceneIndex<0?'OVERVIEW':String(sceneIndex+1).padStart(2,'0')+' / '+String(total).padStart(2,'0')});
 readerScene.querySelectorAll('.scene-current-title').forEach(node=>{node.textContent=title});
 readerScene.querySelectorAll('.scene-mastery').forEach(node=>{node.textContent=document.getElementById('mastery-percent').textContent});
 readerScene.querySelectorAll('.scene-progress').forEach(node=>{node.value=parseInt(document.getElementById('mastery-percent').textContent)||0});
 const excerpt=readerScene.querySelector('.scene-excerpt');if(excerpt)excerpt.textContent=(sceneIndex<0?document.querySelector('#notes>.summary p'):chapters[sceneIndex].querySelector('.prose p'))?.textContent.slice(0,110)||'在当前节点展开完整内容。';
 readerScene.querySelectorAll('[data-scene-action=previous]').forEach(button=>{button.disabled=sceneIndex<=0});readerScene.querySelectorAll('[data-scene-action=next]').forEach(button=>{button.disabled=sceneIndex>=total-1});
}
function selectThemeChapter(index){
 if(!readerScene)return;sceneIndex=Math.max(-1,Math.min(chapters.length-1,index));
 chapters.forEach((chapter,i)=>{chapter.hidden=i!==sceneIndex});sceneExtras.forEach(node=>{node.hidden=sceneIndex>=0});
 updateThemeMeters();currentChapter=-1;queueReading();
}
function applyThemeScene(style,anchor=0){
 if(!themedModes.includes(style))return;
 document.body.dataset.readerTemplate=style;
 readerScene=document.getElementById('reader-'+style).content.firstElementChild.cloneNode(true);document.querySelector('.workspace>main').prepend(readerScene);
 for(const [name,nodes] of Object.entries(sceneNodes))readerScene.querySelector('[data-slot='+name+']').append(...(Array.isArray(nodes)?nodes:[nodes]));
 sceneExtras=Array.from(document.getElementById('notes').children).filter(node=>!node.matches('.chapter,.book-overview'));
 sceneExtraVisibility=new Map(sceneExtras.map(node=>[node,node.hidden]));
 const hashIndex=chapters.findIndex(chapter=>'#'+chapter.id===location.hash);
 selectThemeChapter(hashIndex>=0?hashIndex:style==='whale'&&window.scrollY<96?-1:anchor);
 readerScene.addEventListener('click',event=>{
  const button=event.target.closest('[data-scene-action]');if(!button)return;
  const action=button.dataset.sceneAction;
  if(action==='map'){activate(document.getElementById('tab-map'));return}
  if(action==='encourage'){
   const messages=style==='anime'?['每个难题，都是下一集的伏笔。','暂停一下也没关系，故事不会丢。','能解释给别人听，就是你的主角时刻。']:['慢慢读，今天也能多懂一点。','先看例子，再自己试一遍！','不懂的地方再来一口，知识会消化的。'];
   readerScene.querySelector('.scene-message').textContent=messages[sceneMessage++%messages.length];return;
  }
  activate(document.getElementById('tab-notes'));
  if(action==='overview'){selectThemeChapter(-1);history.replaceState(null,'',location.pathname+location.search);document.getElementById('notes').scrollIntoView({behavior:scrollBehavior(),block:'start'});return}
  goToChapter(action==='previous'?sceneIndex-1:action==='next'?sceneIndex+1:Math.max(0,sceneIndex));
 });
}
document.addEventListener('seagull:chapter',event=>{if(readerScene){activate(document.getElementById('tab-notes'));selectThemeChapter(event.detail)}});
