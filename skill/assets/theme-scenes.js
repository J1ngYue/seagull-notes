// Content remains intact; each reader owns its composition and navigation behavior.
const themedModes=['whale','journal','moonlight','pixel'];
const sceneNodes={heading:document.querySelector('.note-head'),index:document.querySelector('.sidebar'),formats:document.querySelector('.tabs'),panels:Array.from(document.querySelectorAll('.panel[role=tabpanel]'))};
const sceneHomes=new Map();[sceneNodes.heading,sceneNodes.index,sceneNodes.formats,...sceneNodes.panels].forEach(node=>{const marker=document.createComment('reader node home');node.before(marker);sceneHomes.set(node,marker)});
let readerScene=null,sceneIndex=0,sceneExtras=[],sceneExtraVisibility=new Map(),sceneCleanups=[],sceneLastRoute=-1,sceneStudio=null,sceneView='notes',whalePose=0;
const sceneViewOffsets=new Map();
function sceneTitle(index){return chapters[index]?.querySelector('h2').textContent||'学习概览与复习'}
function setSceneReader(open){if(readerScene){readerScene.dataset.readerOpen=String(open);if(open)sceneStudio?.show('reading')}}
function setSceneIndex(open){if(!readerScene)return;readerScene.querySelector('.scene-index').hidden=!open;readerScene.querySelector('[data-scene-action=index]')?.setAttribute('aria-expanded',String(open));if(open)search.focus()}
function unmountThemeScene(){
 if(!readerScene)return;document.querySelector('.mindmap-viewer.expanded [data-map-action=expand]')?.click();sceneCleanups.forEach(cleanup=>cleanup());sceneCleanups=[];
 sceneHomes.forEach((marker,node)=>marker.after(node));chapters.forEach(chapter=>{chapter.hidden=false});sceneExtraVisibility.forEach((hidden,node)=>{node.hidden=hidden});
 readerScene.remove();readerScene=null;sceneExtras=[];sceneExtraVisibility.clear();sceneStudio=null;sceneLastRoute=-1;sceneViewOffsets.clear();delete document.body.dataset.readerTemplate;
}
function getThemeReadingChapter(){
 if(document.body.dataset.style==='whale'||!readerScene||sceneStudio?.screen()!=='reading'||document.body.dataset.view!=='notes')return Math.max(0,sceneIndex);
 const box=readerScene.querySelector('.scene-reader-body').getBoundingClientRect(),rect={top:Math.max(0,box.top),bottom:Math.min(innerHeight,box.bottom),height:box.height};let index=0,visible=0;
 if(!rect.height)return Math.max(0,sceneIndex);
 chapters.forEach((chapter,i)=>{const box=chapter.getBoundingClientRect(),area=Math.max(0,Math.min(rect.bottom,box.bottom)-Math.max(rect.top,box.top));if(area>visible){visible=area;index=i}else if(!visible&&box.top<rect.top)index=i});return index;
}
function setWhalePose(index){whalePose=(index+4)%4;readerScene?.style.setProperty('--whale-active-art','var(--'+['whale-art','whale-explain-art','whale-think-art','whale-celebrate-art'][whalePose]+')')}
function updateOceanRoute(){
 if(!readerScene||!readerScene.matches('.ocean-story')||sceneIndex===sceneLastRoute)return;sceneLastRoute=sceneIndex;
 const host=readerScene.querySelector('.ocean-route'),ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 700 100');
 const start=Math.min(Math.max(0,sceneIndex-3),Math.max(0,chapters.length-7)),slice=chapters.slice(start,start+7),points=slice.map((_,i)=>({x:45+i*610/Math.max(1,slice.length-1),y:30+Math.sin(i*1.2)*9,index:start+i}));
 const path=document.createElementNS(ns,'path');path.setAttribute('d',points.map((point,i)=>i?'C '+((points[i-1].x+point.x)/2)+' '+points[i-1].y+' '+((points[i-1].x+point.x)/2)+' '+point.y+' '+point.x+' '+point.y:'M '+point.x+' '+point.y).join(' '));svg.append(path);
 points.forEach(point=>{const group=document.createElementNS(ns,'g'),circle=document.createElementNS(ns,'circle'),label=document.createElementNS(ns,'text');group.dataset.storyChapter=point.index;group.classList.toggle('active',point.index===sceneIndex);group.setAttribute('role','button');group.setAttribute('tabindex','0');group.setAttribute('aria-label','跳转章节：'+sceneTitle(point.index));circle.setAttribute('cx',point.x);circle.setAttribute('cy',point.y);circle.setAttribute('r',point.index===sceneIndex?9:5);label.setAttribute('x',point.x);label.setAttribute('y',point.y+30);label.textContent=String(point.index+1).padStart(2,'0');group.append(circle,label);svg.append(group)});host.replaceChildren(svg);setWhalePose(Math.max(0,sceneIndex)%4);
}
function updateThemeMeters(){
 if(!readerScene)return;const total=chapters.length,title=sceneTitle(sceneIndex);
 readerScene.querySelectorAll('.scene-position').forEach(node=>{node.textContent=sceneIndex<0?'OVERVIEW':String(sceneIndex+1).padStart(2,'0')+' / '+String(total).padStart(2,'0')});
 readerScene.querySelectorAll('.scene-current-title').forEach(node=>{node.textContent=title});
 readerScene.querySelectorAll('.journal-reading-progress').forEach(node=>{node.max=total;node.value=Math.max(0,sceneIndex+1)});
 readerScene.querySelectorAll('.scene-mastery').forEach(node=>{node.textContent='掌握 '+document.getElementById('mastery-percent').textContent});
 readerScene.querySelectorAll('.study-checklist [data-outline-chapter]').forEach(button=>button.classList.toggle('done',document.querySelector('#chapter-'+(Number(button.dataset.outlineChapter)+1)+' .mastery-button')?.getAttribute('aria-pressed')==='true'));
 const excerpt=readerScene.querySelector('.scene-excerpt');if(excerpt)excerpt.textContent=(sceneIndex<0?document.querySelector('#notes>.summary p'):chapters[sceneIndex]?.querySelector('.prose p'))?.textContent||'打开档案，查看完整解释、代码、图示与出处。';
 readerScene.querySelectorAll('[data-scene-action=previous]').forEach(button=>{button.disabled=sceneIndex<=0});readerScene.querySelectorAll('[data-scene-action=next]').forEach(button=>{button.disabled=sceneIndex>=total-1});
 readerScene.querySelectorAll('[data-outline-chapter]').forEach(button=>{const active=Number(button.dataset.outlineChapter)===sceneIndex;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'location':'false')});
 updateOceanRoute();
}
function selectThemeChapter(index){
 if(!readerScene)return;sceneIndex=Math.max(-1,Math.min(chapters.length-1,index));
 chapters.forEach(chapter=>{chapter.hidden=false});sceneExtras.forEach(node=>{node.hidden=false});
 updateThemeMeters();currentChapter=-1;queueReading();
}
function syncSceneView(){
 if(!readerScene)return;const scroller=readerScene.querySelector('.scene-reader-body');
 if(scroller){sceneViewOffsets.set(sceneView,scroller.scrollTop);scroller.scrollTop=sceneViewOffsets.get(document.body.dataset.view)||0}sceneView=document.body.dataset.view;
 readerScene.querySelectorAll('[data-scene-panel]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.scenePanel===sceneView)));
}
function applyThemeScene(style,anchor=0){
 if(!themedModes.includes(style))return;document.body.dataset.readerTemplate=style;readerScene=document.getElementById('reader-'+style).content.firstElementChild.cloneNode(true);document.querySelector('.workspace>main').prepend(readerScene);
 for(const [name,nodes] of Object.entries(sceneNodes))readerScene.querySelector('[data-slot='+name+']').append(...(Array.isArray(nodes)?nodes:[nodes]));
 readerScene.querySelector('.scene-index').id='scene-index';setSceneIndex(false);
 sceneExtras=Array.from(document.getElementById('notes').children).filter(node=>!node.matches('.chapter,.book-overview'));sceneExtraVisibility=new Map(sceneExtras.map(node=>[node,node.hidden]));
 const hashIndex=chapters.findIndex(chapter=>'#'+chapter.id===location.hash);sceneView=document.body.dataset.view;
 if(style!=='whale')sceneStudio=buildStudio(readerScene,style);
 selectThemeChapter(currentChapter<0&&hashIndex>=0?hashIndex:anchor);syncSceneView();
 if(style!=='whale'&&(hashIndex>=0||sceneView!=='notes'||style==='pixel'&&new URLSearchParams(location.search).get('open')==='notes')){setSceneReader(true);requestAnimationFrame(()=>{if(readerScene&&hashIndex>=0&&sceneView==='notes')chapters[hashIndex].scrollIntoView({block:'start'})})}
 readerScene.addEventListener('click',event=>{
  const route=event.target.closest('[data-story-chapter]'),outline=event.target.closest('[data-outline-chapter]');if(route){goToChapter(Number(route.dataset.storyChapter));return}if(outline){const jump=()=>goToChapter(Number(outline.dataset.outlineChapter));if(sceneStudio?.screen()!=='reading')runReaderTransition(jump);else jump();return}
  const panel=event.target.closest('[data-scene-panel]');if(panel){if(sceneStudio?.screen()==='reading'&&document.body.dataset.view===panel.dataset.scenePanel)return;runReaderTransition(()=>{setSceneReader(true);activate(document.getElementById('tab-'+panel.dataset.scenePanel));syncSceneView()});return}
  const button=event.target.closest('[data-scene-action]');if(!button)return;const action=button.dataset.sceneAction,index=readerScene.querySelector('.scene-index');
  if(action==='pose'){setWhalePose(whalePose+1);return}
  if(action==='index'||action==='close-index'){setSceneIndex(action==='index'&&index.hidden);return}
  if(action==='overview'){runReaderTransition(()=>{activate(document.getElementById('tab-notes'));setSceneReader(true);selectThemeChapter(-1);history.replaceState(null,'',location.pathname+location.search);const target=document.querySelector('#notes>.study-widgets')||document.querySelector('#notes>.summary');target?.scrollIntoView({behavior:scrollBehavior(),block:'start'})});return}
  if(action==='read'){runReaderTransition(()=>{activate(document.getElementById('tab-notes'));setSceneReader(true)});return}activate(document.getElementById('tab-notes'));goToChapter(action==='previous'?sceneIndex-1:action==='next'?sceneIndex+1:Math.max(0,sceneIndex));
 });
 readerScene.addEventListener('keydown',event=>{const route=event.target.closest('[data-story-chapter]');if(route&&(event.key==='Enter'||event.key===' ')){event.preventDefault();goToChapter(Number(route.dataset.storyChapter))}});
}
document.addEventListener('seagull:chapter',event=>{if(!readerScene)return;activate(document.getElementById('tab-notes'));setSceneIndex(false);selectThemeChapter(event.detail);setSceneReader(true)});
document.addEventListener('seagull:position',event=>{if(readerScene){sceneIndex=event.detail;updateThemeMeters()}});
document.addEventListener('seagull:view',()=>{if(readerScene){setSceneReader(true);syncSceneView()}});
document.addEventListener('keydown',event=>{if(event.key!=='Escape'||!readerScene||document.querySelector('dialog[open]'))return;const index=readerScene.querySelector('.scene-index');if(!index.hidden){setSceneIndex(false);readerScene.querySelector('[data-scene-action=index]')?.focus()}});
