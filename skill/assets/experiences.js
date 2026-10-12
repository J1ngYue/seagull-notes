// Each reading mode uses the same complete body, sources and notebook identity.
const stylePicker=document.getElementById('style-select'),routeCards=Array.from(document.querySelectorAll('.route-card'));
const learningKey='seagull:mastery:'+document.body.dataset.noteId,styleKey='seagull:style:'+location.pathname;let mastered=new Set(),folioIndex=0;
function loadPreference(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}}
function savePreference(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{}}
mastered=new Set(loadPreference(learningKey,[]).filter(index=>Number.isInteger(index)&&index>=0&&index<chapters.length));
function updateMastery(){
 const percent=chapters.length?Math.round(mastered.size/chapters.length*100):0;
 document.getElementById('mastery-percent').textContent=percent+'%';document.querySelector('.mastery-orbit').style.setProperty('--mastery',percent+'%');document.getElementById('mastery-count').textContent='已掌握 '+mastered.size+' / '+chapters.length+' 章';document.getElementById('mastery-progress').value=mastered.size;
 chapters.forEach((chapter,index)=>{const button=chapter.querySelector('.mastery-button');button.setAttribute('aria-pressed',String(mastered.has(index)));button.textContent=mastered.has(index)?'已掌握 · 点击撤销':'标记已掌握';routeCards[index].classList.toggle('is-mastered',mastered.has(index))});
}
chapters.forEach((chapter,index)=>{const button=document.createElement('button');button.type='button';button.className='mastery-button';button.setAttribute('aria-label','切换掌握状态：'+chapter.querySelector('h2').textContent);button.addEventListener('click',()=>{mastered.has(index)?mastered.delete(index):mastered.add(index);savePreference(learningKey,Array.from(mastered));updateMastery()});chapter.append(button)});
function selectFolioChapter(index){
 folioIndex=Math.max(0,Math.min(chapters.length-1,index));
 document.body.classList.toggle('journal-reading',folioIndex>0);
 chapters.forEach((chapter,position)=>{chapter.classList.toggle('folio-current',position===folioIndex)});
 document.getElementById('folio-position').textContent=String(folioIndex+1).padStart(2,'0')+' / '+chapters.length;
 document.querySelector('[data-folio=previous]').disabled=folioIndex===0;document.querySelector('[data-folio=next]').disabled=folioIndex===chapters.length-1;
 const grid=document.querySelector('.route-grid'),card=routeCards[folioIndex],g=grid.getBoundingClientRect(),c=card.getBoundingClientRect();if(c.left<g.left||c.right>g.right)grid.scrollTo({left:grid.scrollLeft+c.left-g.left-(grid.clientWidth-card.offsetWidth)/2,behavior:scrollBehavior()});
}
function applyReadingStyle(style){
 if(!['paper','atlas','folio'].includes(style))style='paper';document.body.dataset.style=style;stylePicker.value=style;
 document.querySelector('.hub-heading .label').textContent=style==='folio'?'MY STUDY JOURNAL':'MY STUDY NOTES';document.querySelector('.hub-heading h2').textContent=style==='folio'?'翻开这一页，继续理解。':'把重点写在纸上。';document.querySelector('.hub-heading p').textContent=style==='folio'?'从目录选一章，或用左右键继续阅读。':chapters.length+' 个章节，保留完整学习内容。';
 if(style==='folio'){const index=chapters.findIndex(chapter=>'#'+chapter.id===location.hash);selectFolioChapter(index>=0?index:Math.max(0,currentChapter))}
 currentChapter=-1;queueReading();requestAnimationFrame(updateIndicator);
}
stylePicker.addEventListener('change',()=>{applyReadingStyle(stylePicker.value);savePreference(styleKey,stylePicker.value)});
document.addEventListener('seagull:chapter',event=>{if(document.body.dataset.style==='folio')selectFolioChapter(event.detail)});
document.addEventListener('seagull:position',event=>{routeCards.forEach((card,index)=>card.classList.toggle('is-current',index===event.detail));if(document.body.dataset.style==='folio')selectFolioChapter(event.detail)});
routeCards.forEach((card,index)=>card.addEventListener('click',()=>{activate(document.getElementById('tab-notes'));goToChapter(index)}));
document.querySelector('[data-folio=previous]').addEventListener('click',()=>goToChapter(folioIndex-1));document.querySelector('[data-folio=next]').addEventListener('click',()=>goToChapter(folioIndex+1));
document.addEventListener('keydown',event=>{if(event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||document.body.dataset.style!=='folio'||document.body.dataset.view!=='notes'||event.target.closest('input,textarea,select,pre,dialog,[role=tab]'))return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();goToChapter(folioIndex+(event.key==='ArrowRight'?1:-1))}});
applyReadingStyle(loadPreference(styleKey,document.body.dataset.style));updateMastery();
const chapterReveal=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');chapterReveal.unobserve(entry.target)}}),{threshold:.08});chapters.forEach(chapter=>chapterReveal.observe(chapter));
document.querySelectorAll('.explorer').forEach(explorer=>{
 const buttons=Array.from(explorer.querySelectorAll('[data-step]')),panels=Array.from(explorer.querySelectorAll('.explore-panel')),play=explorer.querySelector('.explore-play');let selected=0,timer=null;
 function stop(){clearInterval(timer);timer=null;play.textContent='自动演示';play.setAttribute('aria-pressed','false')}
 function select(index){selected=(index+buttons.length)%buttons.length;buttons.forEach((button,position)=>{button.setAttribute('aria-selected',String(position===selected));button.tabIndex=position===selected?0:-1});panels.forEach((panel,position)=>{panel.hidden=position!==selected});explorer.querySelector('progress').value=selected+1}
 buttons.forEach((button,index)=>{button.addEventListener('click',()=>{stop();select(index)});button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();stop();select(event.key==='Home'?0:event.key==='End'?buttons.length-1:index+(event.key==='ArrowRight'?1:-1));buttons[selected].focus()}})});
 play.addEventListener('click',()=>{if(timer){stop();return}play.textContent='暂停演示';play.setAttribute('aria-pressed','true');timer=setInterval(()=>{select(selected+1);if(selected===buttons.length-1)stop()},1800)});
 document.addEventListener('seagull:view',event=>{if(event.detail!=='notes')stop()});document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});
});
let printDetails=[];window.addEventListener('beforeprint',()=>{printDetails=Array.from(document.querySelectorAll('details')).map(item=>[item,item.open]);printDetails.forEach(([item])=>{item.open=true})});window.addEventListener('afterprint',()=>{printDetails.forEach(([item,open])=>{item.open=open});printDetails=[]});
