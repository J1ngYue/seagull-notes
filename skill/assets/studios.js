// The three screenshot-based workspaces share data, while keeping separate markup.
function buildStudio(root,style){
 const shelf=JSON.parse(document.getElementById('shelf-data').textContent),heading=sceneNodes.heading;
 root.querySelectorAll('.shelf-count').forEach(node=>node.textContent=shelf.entries.length);
 root.querySelectorAll('.chapter-count').forEach(node=>node.textContent=chapters.length);
 root.querySelectorAll('.studio-summary').forEach(node=>node.textContent=document.querySelector('#notes>.summary p')?.textContent||heading.querySelector('.subtitle')?.textContent||'');
 let screen='',drag=null;const positions=new Map();
 function show(next){
  if(next===screen){const main=root.querySelector('[data-window=notes]');if(main&&next!=='desktop'){main.hidden=false;updateTasks()}return}const scroller=root.querySelector('.scene-reader-body');if(screen==='reading'&&scroller)positions.set(document.body.dataset.view,scroller.scrollTop);
  const previousScreen=screen;screen=next;root.dataset.screen=next;root.querySelectorAll('.studio-home,.studio-shelf,.studio-reading').forEach(node=>{node.hidden=!node.classList.contains('studio-'+next);if(!node.hidden)node.dataset.screenPanel=next});
  root.querySelectorAll('[data-studio-action=home],[data-studio-action=shelf]').forEach(button=>button.classList.toggle('active',button.dataset.studioAction===next));
  const title=root.querySelector('.pixel-window-title');if(title)title.textContent=next==='reading'?heading.querySelector('h1').textContent:'我的笔记';
  const main=root.querySelector('[data-window=notes]');if(main){main.hidden=next==='desktop';main.style.zIndex='20';
   const opened=next==='reading';root.dataset.fileOpen=String(opened);root.querySelector('.pixel-file-icons').hidden=!opened;
   root.querySelectorAll('[data-window=outline]').forEach(panel=>panel.hidden=!opened);root.querySelector('[data-window-restore=outline]').hidden=!opened;
   root.querySelector('.pixel-address').textContent='我的电脑 / 我的笔记'+(opened?' / '+heading.querySelector('h1').textContent:'');
   root.querySelector('.pixel-file-status').textContent=opened?'笔记已打开':shelf.entries.length+' 个笔记文件';
   root.querySelector('[data-window-restore=notes]').hidden=next==='desktop';
   if(next==='desktop'&&previousScreen){const url=new URL(location.href);url.searchParams.delete('open');url.hash='';history.replaceState(null,'',url.pathname+url.search)}
   updateTasks();
  }
  if(next==='reading'&&scroller)scroller.scrollTop=positions.get(document.body.dataset.view)||0;
 }
 function card(entry){
  const link=document.createElement('a');link.className='shelf-card';link.href=entry.current?'#':entry.href+(entry.href.includes('?')?'&':'?')+'style='+style+(style==='pixel'?'&open=notes':'');link.dataset.shelfSearch=[entry.title,entry.summary,...entry.tags].join(' ').toLowerCase();
  const art=document.createElement('div'),cover=entry.cover||(entry.current?document.querySelector('#notes .cover img')?.src:'');art.className='shelf-card-art';if(cover){const img=document.createElement('img');img.src=cover;img.alt='';img.loading='lazy';art.append(img)}else{art.classList.add('placeholder');art.textContent='▤'}
  const body=document.createElement('div');body.className='shelf-card-body';const title=document.createElement('h3'),summary=document.createElement('p'),meta=document.createElement('small');title.textContent=entry.title;summary.textContent=entry.summary;meta.textContent=entry.chapters+' 个章节 · '+entry.platform;body.append(title,summary,meta);link.append(art,body);
  if(entry.current)link.addEventListener('click',event=>{event.preventDefault();activate(document.getElementById('tab-notes'));show('reading');if(style==='pixel')history.replaceState(null,'',location.pathname+'?style=pixel&open=notes')});return link;
 }
 root.querySelectorAll('.shelf-cards').forEach(host=>{(host.classList.contains('home-cards')?shelf.entries.slice(0,4):shelf.entries).forEach(entry=>host.append(card(entry)))});
 root.querySelectorAll('.outline-chapters,.sidebar-chapters,.study-checklist').forEach(host=>chapters.forEach((chapter,index)=>{const button=document.createElement('button');button.type='button';button.dataset.outlineChapter=index;button.textContent=(host.classList.contains('study-checklist')?'':String(index+1).padStart(2,'0')+'  ')+sceneTitle(index);host.append(button)}));
 function filterShelf(query){show('shelf');let count=0;root.querySelectorAll('.all-cards .shelf-card').forEach(card=>{card.hidden=!card.dataset.shelfSearch.includes(query.trim().toLowerCase());if(!card.hidden)count++});root.querySelectorAll('.shelf-empty').forEach(node=>node.hidden=count>0)}
 root.querySelectorAll('.shelf-search').forEach(input=>input.addEventListener('input',()=>filterShelf(input.value)));
 if(style==='journal'){
  const today=new Date(),month=new Date(today.getFullYear(),today.getMonth(),1),grid=root.querySelector('.calendar-days');
  function calendar(){root.querySelector('.calendar-title').textContent=month.getFullYear()+'  |  '+String(month.getMonth()+1).padStart(2,'0')+'月';grid.replaceChildren();for(let i=0;i<month.getDay();i++)grid.append(document.createElement('span'));for(let i=1;i<=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();i++){const day=document.createElement('span');day.textContent=i;if(i===today.getDate()&&month.getMonth()===today.getMonth()&&month.getFullYear()===today.getFullYear()){day.classList.add('today');day.setAttribute('aria-label','今天 '+i+' 日')}grid.append(day)}}
  root.querySelectorAll('[data-journal-month]').forEach(button=>button.addEventListener('click',()=>{month.setMonth(month.getMonth()+Number(button.dataset.journalMonth));calendar()}));calendar();
  const memo=root.querySelector('.journal-memo-input'),memoKey='seagull:journal:memo';memo.value=loadPreference(memoKey,'');memo.addEventListener('input',()=>{savePreference(memoKey,memo.value);root.querySelector('.journal-memo-status').textContent='已自动保存在本地'});
  const tags=new Map();shelf.entries.forEach(entry=>entry.tags.forEach(tag=>tags.set(tag,(tags.get(tag)||0)+1)));const tagHost=root.querySelector('.journal-tags');tags.forEach((count,tag)=>{const button=document.createElement('button'),label=document.createElement('span'),number=document.createElement('small');button.type='button';label.textContent='#  '+tag;number.textContent=count;button.append(label,number);button.addEventListener('click',()=>{root.querySelector('.shelf-search').value=tag;filterShelf(tag)});tagHost.append(button)});if(!tags.size)tagHost.hidden=true;
  shelf.entries.slice(0,4).forEach(entry=>{const link=card(entry);link.classList.add('recent-note');root.querySelector('.journal-recent-list').append(link)});
 }
 root.addEventListener('click',event=>{
  const button=event.target.closest('[data-studio-action]');if(button){event.preventDefault();const action=button.dataset.studioAction;if(['home','shelf','desktop'].includes(action)){show(action);return}if(action==='print')window.print();if(action==='export')document.querySelector('.obsidian-link')?.click()}
  const windowButton=event.target.closest('[data-window-action]');if(windowButton){const panel=windowButton.closest('[data-window]'),action=windowButton.dataset.windowAction;if(action==='minimize')panel.hidden=true;else if(action==='maximize')panel.classList.toggle('maximized');else show(style==='pixel'?'desktop':'home');updateTasks()}
  const restore=event.target.closest('[data-window-restore]');if(restore){const panel=root.querySelector('[data-window='+restore.dataset.windowRestore+']');panel.hidden=false;root.querySelectorAll('[data-window]').forEach(node=>node.style.zIndex=node===panel?'25':'8');updateTasks()}
 });
 function updateTasks(){root.querySelectorAll('[data-window-restore]').forEach(button=>button.setAttribute('aria-pressed',String(!root.querySelector('[data-window='+button.dataset.windowRestore+']').hidden)))}
 function key(event){if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();const input=root.querySelector('.shelf-search');input?.focus()}}
 document.addEventListener('keydown',key);sceneCleanups.push(()=>document.removeEventListener('keydown',key));
 if(style==='pixel'){
  root.addEventListener('pointerdown',event=>{const bar=event.target.closest('.pixel-titlebar');if(!bar||event.target.closest('button')||event.button!==0||innerWidth<700)return;const panel=bar.closest('[data-window]');if(panel.classList.contains('maximized'))return;const rect=panel.getBoundingClientRect();drag={panel,id:event.pointerId,x:event.clientX,y:event.clientY,left:rect.left,top:rect.top};panel.style.position='fixed';panel.style.left=rect.left+'px';panel.style.top=rect.top+'px';panel.style.right='auto';panel.style.width=rect.width+'px';panel.style.zIndex='30';bar.setPointerCapture(event.pointerId)});
  root.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;drag.panel.style.left=Math.max(0,Math.min(innerWidth-180,drag.left+event.clientX-drag.x))+'px';drag.panel.style.top=Math.max(0,Math.min(innerHeight-90,drag.top+event.clientY-drag.y))+'px'});
  root.addEventListener('pointerup',()=>drag=null);root.addEventListener('pointercancel',()=>drag=null);updateTasks();
 }
 root.querySelector('.scene-reader-body')?.addEventListener('scroll',queueReading,{passive:true});
 root.querySelectorAll('[data-studio-action=export]').forEach(button=>button.hidden=!document.querySelector('.obsidian-link'));
 show(style==='pixel'?'desktop':'home');return {show,screen:()=>screen};
}
