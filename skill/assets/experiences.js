// Each reading mode uses the same complete body, sources and notebook identity.
const stylePicker=document.getElementById('style-select'),routeCards=Array.from(document.querySelectorAll('.route-card'));
const notebookTools=document.querySelector('.topbar'),toolsToggle=document.getElementById('tools-toggle'),formatTabs=document.querySelector('.tabs'),tabsHome=formatTabs.parentElement,tabsNext=formatTabs.nextElementSibling;
const overview=document.createElement('details');overview.className='book-overview';const overviewTitle=document.createElement('summary');overviewTitle.textContent='概览、重点与配图';overview.append(overviewTitle);const introPieces=Array.from(document.querySelectorAll('#notes>.summary,#notes>.takeaways,#notes>.cover'));document.getElementById('notes').prepend(overview);
function closeNotebookTools(){notebookTools.classList.remove('tools-open');toolsToggle.setAttribute('aria-expanded','false')}
toolsToggle.addEventListener('click',()=>{const open=notebookTools.classList.toggle('tools-open');toolsToggle.setAttribute('aria-expanded',String(open));requestAnimationFrame(updateIndicator)});
document.addEventListener('seagull:view',closeNotebookTools);
document.addEventListener('click',event=>{if(!notebookTools.contains(event.target))closeNotebookTools()});document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeNotebookTools();sidebar.classList.remove('toc-open');tocToggle.setAttribute('aria-expanded','false')}});
const learningKey='seagull:mastery:'+document.body.dataset.noteId,styleKey='seagull:style:'+location.pathname;let mastered=new Set(),folioIndex=0;
function loadPreference(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}}
function savePreference(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{}}
mastered=new Set(loadPreference(learningKey,[]).filter(index=>Number.isInteger(index)&&index>=0&&index<chapters.length));
const notePanel=document.getElementById('notes'),bookSpread=document.createElement('div');bookSpread.className='book-spread';bookSpread.setAttribute('role','region');bookSpread.setAttribute('aria-label','左右双页笔记书');
const overviewHome=document.createComment('overview home');overview.before(overviewHome);
const bookExtra=Array.from(notePanel.children).filter(element=>element.classList.contains('study-widgets')||element.classList.contains('source-list'));
const masteryButtons=[];let bookPages=[],pagination=null,openedBookDetails=[],paginationFrame=0,bookLayoutKey='';
const bookEdges=['previous','next'].map(direction=>{const button=document.createElement('button');button.type='button';button.className='book-edge book-edge-'+direction;button.setAttribute('aria-label',direction==='next'?'翻到下一组页面':'翻到上一组页面');button.innerHTML='<span class="book-edge-arrow" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="'+(direction==='next'?'m9 5 7 7-7 7':'m15 5-7 7 7 7')+'"/></svg></span>';button.addEventListener('click',()=>turnBook(direction==='next'?1:-1));return button});
let bookMounted=false,overviewBeforeBook=false,bookAnimation=null,bookLayers=[];
function pagesPerSpread(){return matchMedia('(max-width:700px)').matches?1:2}
function bookRange(index){const size=pagesPerSpread(),start=Math.floor(index/size)*size;return {start,end:Math.min(start+size,bookPages.length),size}}
function getFolioReadingChapter(){return Math.max(0,Math.min(Number(bookPages[folioIndex]?.dataset.chapter)||0,chapters.length-1))}
function stopBookAnimation(){if(bookAnimation){bookAnimation.cancel();bookAnimation=null}bookLayers.forEach(layer=>layer.remove());bookLayers=[];bookSpread.removeAttribute('aria-busy')}
function bindBookMath(root){root.querySelectorAll('.arithmatex[data-latex]').forEach(element=>{if(element.dataset.copyBound)return;element.dataset.copyBound='true';element.addEventListener('click',()=>copyFormula(element));element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();copyFormula(element)}})})}
function bookDocuments(){
 const documents=chapters.map((chapter,index)=>({chapter:index,header:chapter.querySelector('header'),sources:Array.from(chapter.children).filter(element=>!element.matches('header,.mastery-button')),footer:masteryButtons[index]}));
 const last=Math.max(0,chapters.length-1);
 if(introPieces.length){const heading=document.createElement('h2');heading.textContent='概览与重点';documents.push({chapter:last,header:heading,sources:introPieces})}
 if(bookExtra.length){const heading=document.createElement('h2');heading.textContent='复习与资料';documents.push({chapter:last,header:heading,sources:bookExtra})}
 return documents;
}
function rebuildBook(){
 if(!bookMounted||document.body.dataset.view!=='notes'||!bookSpread.clientHeight)return;stopBookAnimation();
 const anchor=pagination?.starts[folioIndex],focus=getFolioReadingChapter();if(pagination)pagination.restore();bookSpread.replaceChildren();bookPages=[];
 pagination=paginateNotebookBook(bookSpread,bookDocuments(),{reflow:scheduleBookPagination,bindMath:bindBookMath});bookPages=pagination.pages;
 if(bookPages.length%2){const page=document.createElement('section');page.className='book-page';page.id='book-page-'+(bookPages.length+1);page.dataset.chapter=String(focus);const body=document.createElement('div');body.className='book-page-body';const title=document.createElement('h2');title.textContent=document.querySelector('h1').textContent;const meta=document.createElement('p');meta.className='book-source-description';meta.textContent=document.querySelector('.meta').textContent;body.append(title,meta);const list=document.createElement('ul');Array.from(new Set([0,Math.floor(chapters.length/2),chapters.length-1])).filter(index=>chapters[index]).forEach(index=>{const item=document.createElement('li'),link=document.createElement('a');link.href='#'+chapters[index].id;link.textContent=chapters[index].querySelector('h2').textContent;link.addEventListener('click',event=>{event.preventDefault();goToChapter(index)});item.append(link);list.append(item)});body.append(list);const footer=document.createElement('footer');footer.className='book-page-footer';footer.textContent=String(bookPages.length+1);page.append(body,footer);bookSpread.append(page);bookPages.push(page)}
 bookSpread.append(...bookEdges);bookLayoutKey=bookSpread.clientWidth+'x'+bookSpread.clientHeight;
 let target=pagination.chapterPages.get(focus)||0;if(anchor){pagination.starts.forEach((start,index)=>{if(start&&start.node===anchor.node&&start.offset<=anchor.offset)target=index})}
 selectBookPage(target,false);currentChapter=-1;queueReading();
}
function scheduleBookPagination(){if(!paginationFrame)paginationFrame=requestAnimationFrame(()=>{paginationFrame=0;rebuildBook()})}
function mountBook(){
 if(bookMounted)return;overviewBeforeBook=overview.open;openedBookDetails=bookExtra.flatMap(root=>Array.from(root.querySelectorAll('details'))).map(item=>[item,item.open]);openedBookDetails.forEach(([item])=>{item.open=true});notePanel.prepend(bookSpread);bookMounted=true;rebuildBook();
}
function unmountBook(){
 if(!bookMounted)return;stopBookAnimation();if(pagination)pagination.restore();bookSpread.replaceChildren();overviewHome.after(overview);overview.open=overviewBeforeBook;openedBookDetails.forEach(([item,open])=>{item.open=open});bookSpread.remove();bookPages=[];pagination=null;bookMounted=false;
}
function updateBookControls(){
 const range=bookRange(folioIndex),busy=!!bookAnimation,last=range.end>=bookPages.length;
 document.getElementById('folio-position').textContent=(range.start+1)+(range.end>range.start+1?' — '+range.end:'')+' / '+bookPages.length;
 document.querySelector('[data-folio=previous]').disabled=busy||range.start===0;document.querySelector('[data-folio=next]').disabled=busy||last;
 bookEdges[0].disabled=busy||range.start===0;bookEdges[1].disabled=busy||last;
}
function pageSnapshot(page){const clone=page.cloneNode(true);clone.removeAttribute('id');clone.querySelectorAll('[id]').forEach(element=>element.removeAttribute('id'));clone.setAttribute('aria-hidden','true');clone.setAttribute('inert','');clone.classList.add('book-page-snapshot','folio-visible');clone.style.cssText='width:100%;height:100%;margin:0;position:static;transform:none;overflow:hidden';return clone}
function animateBookTurn(previousRange,nextRange){
 const forward=nextRange.start>previousRange.start,turning=bookPages[forward?previousRange.end-1:previousRange.start],reveal=bookPages[forward?nextRange.start:nextRange.end-1];
 const layer=document.createElement('div');layer.className='book-turn-leaf '+(forward?'turn-forward':'turn-backward');layer.setAttribute('aria-hidden','true');layer.setAttribute('inert','');
 const front=document.createElement('div'),back=document.createElement('div');front.className='book-turn-face book-turn-front';back.className='book-turn-face book-turn-back';
 const oldCopy=pageSnapshot(turning),newCopy=pageSnapshot(reveal);front.append(oldCopy);back.append(newCopy);layer.append(front,back);bookSpread.append(layer);oldCopy.scrollTop=turning.scrollTop;newCopy.scrollTop=reveal.scrollTop;bookLayers.push(layer);
 if(previousRange.size===2){const held=bookPages[forward?previousRange.start:previousRange.end-1],hold=document.createElement('div');hold.className='book-held-page '+(forward?'book-held-left':'book-held-right');hold.setAttribute('aria-hidden','true');hold.setAttribute('inert','');const copy=pageSnapshot(held);hold.append(copy);bookSpread.append(hold);copy.scrollTop=held.scrollTop;bookLayers.push(hold)}
 const duration=previousRange.size===2?720:420,end=previousRange.size===2?(forward?-180:180):(forward?-100:100);
 bookAnimation=layer.animate([{transform:'rotateY(0deg)',offset:0},{transform:'rotateY('+(end*.48)+'deg)',offset:.48},{transform:'rotateY('+end+'deg)',offset:1}],{duration,easing:'cubic-bezier(.35,.05,.2,1)',fill:'forwards'});
 bookSpread.setAttribute('aria-busy','true');updateBookControls();const running=bookAnimation;running.finished.then(()=>{if(bookAnimation===running){stopBookAnimation();updateBookControls()}},()=>{});
}
function updateMastery(){
 const percent=chapters.length?Math.round(mastered.size/chapters.length*100):0;
 document.getElementById('mastery-percent').textContent=percent+'%';document.querySelector('.mastery-orbit').style.setProperty('--mastery',percent+'%');document.getElementById('mastery-count').textContent='已掌握 '+mastered.size+' / '+chapters.length+' 章';document.getElementById('mastery-progress').value=mastered.size;
 chapters.forEach((chapter,index)=>{const button=masteryButtons[index];button.setAttribute('aria-pressed',String(mastered.has(index)));button.textContent=mastered.has(index)?'已掌握 · 点击撤销':'标记已掌握';routeCards[index].classList.toggle('is-mastered',mastered.has(index))});
}
chapters.forEach((chapter,index)=>{const button=document.createElement('button');button.type='button';button.className='mastery-button';button.setAttribute('aria-label','切换掌握状态：'+chapter.querySelector('h2').textContent);button.addEventListener('click',()=>{mastered.has(index)?mastered.delete(index):mastered.add(index);savePreference(learningKey,Array.from(mastered));updateMastery()});chapter.append(button);masteryButtons.push(button)});
function selectFolioChapter(index,animate=true){selectBookPage(pagination?.chapterPages.get(index)||0,animate)}
function selectBookPage(index,animate=true){
 const previousRange=bookRange(folioIndex),target=Math.max(0,Math.min(bookPages.length-1,index)),nextRange=bookRange(target),changed=previousRange.start!==nextRange.start;
 stopBookAnimation();folioIndex=target;document.body.dataset.bookLayout=nextRange.size===2?'spread':'single';
 if(animate&&changed&&bookMounted&&document.body.dataset.view==='notes'&&!matchMedia('(prefers-reduced-motion: reduce)').matches)animateBookTurn(previousRange,nextRange);
 bookPages.forEach((page,position)=>{const visible=position>=nextRange.start&&position<nextRange.end;page.classList.toggle('folio-visible',visible);page.classList.toggle('folio-current',position===folioIndex);page.classList.toggle('book-left',visible&&position===nextRange.start);page.classList.toggle('book-right',visible&&position===nextRange.start+1);page.setAttribute('aria-hidden',String(!visible))});
 updateBookControls();
}
function turnBook(direction){
 if(bookAnimation)return;const range=bookRange(folioIndex),target=direction>0?range.end:range.start-range.size;if(target<0||target>=bookPages.length)return;
 selectBookPage(target);history.replaceState(null,'','#'+bookPages[target].id);currentChapter=-1;queueReading();
}
function applyReadingStyle(style){
 if(!['paper','atlas','folio'].includes(style))style='paper';document.body.dataset.style=style;stylePicker.value=style;
 if(bookMounted)unmountBook();
 if(style==='paper'){tabsHome.insertBefore(formatTabs,tabsNext);introPieces.forEach(piece=>overview.before(piece));overview.hidden=true}else{document.getElementById('reader-tools').append(formatTabs);introPieces.forEach(piece=>overview.append(piece));overview.hidden=false}
 closeNotebookTools();
 document.querySelector('.hub-heading .label').textContent=style==='folio'?'MY STUDY JOURNAL':'MY STUDY NOTES';document.querySelector('.hub-heading h2').textContent=style==='folio'?'翻开这一页，继续理解。':'把重点写在纸上。';document.querySelector('.hub-heading p').textContent=style==='folio'?'从目录选一章，或用左右键继续阅读。':chapters.length+' 个章节，保留完整学习内容。';
 if(style==='folio'){mountBook();const index=bookPages.findIndex(page=>'#'+page.id===location.hash),chapter=chapters.findIndex(page=>'#'+page.id===location.hash);if(index>=0)selectBookPage(index,false);else selectFolioChapter(chapter>=0?chapter:Math.max(0,currentChapter),false);window.scrollTo({top:0,behavior:'auto'})}
 currentChapter=-1;queueReading();requestAnimationFrame(updateIndicator);
}
stylePicker.addEventListener('change',()=>{applyReadingStyle(stylePicker.value);savePreference(styleKey,stylePicker.value)});
document.addEventListener('seagull:chapter',event=>{if(document.body.dataset.style==='folio')selectFolioChapter(event.detail)});
document.addEventListener('seagull:position',event=>{routeCards.forEach((card,index)=>card.classList.toggle('is-current',index===event.detail))});
routeCards.forEach((card,index)=>card.addEventListener('click',()=>{activate(document.getElementById('tab-notes'));goToChapter(index)}));
document.querySelector('[data-folio=previous]').addEventListener('click',()=>turnBook(-1));document.querySelector('[data-folio=next]').addEventListener('click',()=>turnBook(1));
document.addEventListener('keydown',event=>{if(event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||document.body.dataset.style!=='folio'||document.body.dataset.view!=='notes'||event.target.closest('input,textarea,select,pre,dialog,[role=tab]'))return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();turnBook(event.key==='ArrowRight'?1:-1)}});
new ResizeObserver(()=>{if(bookMounted&&bookSpread.clientHeight&&bookLayoutKey!==bookSpread.clientWidth+'x'+bookSpread.clientHeight)scheduleBookPagination()}).observe(bookSpread);document.fonts.ready.then(()=>{if(bookMounted)scheduleBookPagination()});document.querySelectorAll('#notes img').forEach(image=>image.addEventListener('load',()=>{if(bookMounted)scheduleBookPagination()}));document.addEventListener('click',event=>{if(bookMounted&&event.target.closest('.wrap-code'))scheduleBookPagination()});document.addEventListener('seagull:view',()=>{stopBookAnimation();if(bookMounted&&document.body.dataset.view==='notes')scheduleBookPagination()});
applyReadingStyle(loadPreference(styleKey,document.body.dataset.style));updateMastery();
const chapterReveal=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');chapterReveal.unobserve(entry.target)}}),{threshold:.08});chapters.forEach(chapter=>chapterReveal.observe(chapter));
document.querySelectorAll('.explorer').forEach(explorer=>{
 const buttons=Array.from(explorer.querySelectorAll('[data-step]')),panels=Array.from(explorer.querySelectorAll('.explore-panel')),play=explorer.querySelector('.explore-play');let selected=0,timer=null;
 function stop(){clearInterval(timer);timer=null;play.textContent='自动演示';play.setAttribute('aria-pressed','false')}
 function select(index){selected=(index+buttons.length)%buttons.length;buttons.forEach((button,position)=>{button.setAttribute('aria-selected',String(position===selected));button.tabIndex=position===selected?0:-1});panels.forEach((panel,position)=>{panel.hidden=position!==selected});explorer.querySelector('progress').value=selected+1;if(bookMounted)scheduleBookPagination()}
 buttons.forEach((button,index)=>{button.addEventListener('click',()=>{stop();select(index)});button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();stop();select(event.key==='Home'?0:event.key==='End'?buttons.length-1:index+(event.key==='ArrowRight'?1:-1));buttons[selected].focus()}})});
 play.addEventListener('click',()=>{if(timer){stop();return}play.textContent='暂停演示';play.setAttribute('aria-pressed','true');timer=setInterval(()=>{select(selected+1);if(selected===buttons.length-1)stop()},1800)});
 document.addEventListener('seagull:view',event=>{if(event.detail!=='notes')stop()});document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});
});
let printDetails=[];window.addEventListener('beforeprint',()=>{stopBookAnimation();printDetails=Array.from(document.querySelectorAll('details')).map(item=>[item,item.open]);printDetails.forEach(([item])=>{item.open=true})});window.addEventListener('afterprint',()=>{printDetails.forEach(([item,open])=>{item.open=open});printDetails=[];if(bookMounted)updateBookControls()});
