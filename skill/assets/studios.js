// The three screenshot-based workspaces share data, while keeping separate markup.
function resizePixelWindow(rect,dx,dy,direction,bounds,minWidth,minHeight){
 const right=rect.left+rect.width,bottom=rect.top+rect.height;
 const west=direction.includes('w'),east=direction.includes('e'),north=direction.includes('n'),south=direction.includes('s');
 const clamp=(value,minimum,maximum)=>Math.max(Math.min(minimum,maximum),Math.min(maximum,value));
 let left=rect.left,top=rect.top,width=rect.width,height=rect.height;
 if(direction.length===2){
  const anchorX=west?right:left,anchorY=north?bottom:top;
  const maxWidth=west?anchorX-bounds.left:bounds.right-anchorX,maxHeight=north?anchorY-bounds.top:bounds.bottom-anchorY;
  const maximum=Math.min(maxWidth/width,maxHeight/height),minimum=Math.max(minWidth/width,minHeight/height);
  const movement=((west?-dx:dx)*width+(north?-dy:dy)*height)/(width*width+height*height);
  const scale=clamp(1+movement,minimum,maximum);width*=scale;height*=scale;
  left=west?anchorX-width:anchorX;top=north?anchorY-height:anchorY;
 }else{
  if(east)width=clamp(width+dx,minWidth,bounds.right-left);
  if(west){left=clamp(left+dx,bounds.left,right-minWidth);width=right-left}
  if(south)height=clamp(height+dy,minHeight,bounds.bottom-top);
  if(north){top=clamp(top+dy,bounds.top,bottom-minHeight);height=bottom-top}
 }
 return {left,top,width,height};
}
function buildJournalMemos(root){
 const host=root.querySelector('.journal-quick-memo'),list=host.querySelector('.journal-memo-list'),status=host.querySelector('.journal-memo-status'),empty=host.querySelector('.journal-memo-empty'),undo=host.querySelector('.journal-memo-undo');
 const key='seagull:journal:memos',saved=loadPreference(key,null),legacy=loadPreference('seagull:journal:memo','');
 const make=text=>({id:crypto.randomUUID(),text,done:false});
 let memos=Array.isArray(saved)?saved.filter(item=>item&&typeof item.text==='string'):(typeof legacy==='string'&&legacy? [make(legacy)]:['记录今天想学的知识','整理自己的笔记','保持创作的节奏！'].map(make)),removed=null;
 function persist(){try{localStorage.setItem(key,JSON.stringify(memos));status.textContent='已自动保存 · 仅此浏览器'}catch{status.textContent='本地保存不可用，请先复制内容'}}
 function size(input){input.style.height='auto';input.style.height=Math.min(170,Math.max(30,input.scrollHeight))+'px'}
 function append(memo){
  const row=document.createElement('div');row.className='journal-memo-row';row.dataset.memoId=memo.id;row.classList.toggle('done',memo.done);
  const check=document.createElement('input');check.type='checkbox';check.className='journal-memo-check';check.checked=!!memo.done;check.setAttribute('aria-label','标记便笺完成');
  const input=document.createElement('textarea');input.className='journal-memo-input';input.rows=1;input.value=memo.text;input.placeholder='写下新的便笺…';input.setAttribute('aria-label','便笺内容');
  const remove=document.createElement('button');remove.type='button';remove.className='journal-memo-delete';remove.textContent='×';remove.title='删除这条便笺';remove.setAttribute('aria-label','删除便笺');
  check.addEventListener('change',()=>{memo.done=check.checked;row.classList.toggle('done',memo.done);persist()});
  input.addEventListener('input',()=>{memo.text=input.value;size(input);persist()});
  remove.addEventListener('click',()=>{const index=memos.indexOf(memo);removed={memo,index};memos.splice(index,1);row.remove();empty.hidden=memos.length>0;undo.hidden=false;persist();(list.querySelector('.journal-memo-input')||host.querySelector('.journal-memo-add')).focus()});
  row.append(check,input,remove);list.append(row);size(input);return input;
 }
 memos.forEach(append);empty.hidden=memos.length>0;
 host.querySelector('.journal-memo-add').addEventListener('click',()=>{const memo=make('');memos.push(memo);const input=append(memo);empty.hidden=true;persist();input.focus()});
 undo.addEventListener('click',()=>{if(!removed)return;memos.splice(removed.index,0,removed.memo);removed=null;undo.hidden=true;list.replaceChildren();memos.forEach(append);empty.hidden=true;persist()});
 const observer=new ResizeObserver(()=>list.querySelectorAll('.journal-memo-input').forEach(size));observer.observe(list);sceneCleanups.push(()=>observer.disconnect());
}
function buildStudio(root,style){
 const shelf=JSON.parse(document.getElementById('shelf-data').textContent),heading=sceneNodes.heading;
 root.querySelectorAll('.shelf-count').forEach(node=>node.textContent=shelf.entries.length);
 root.querySelectorAll('.chapter-count').forEach(node=>node.textContent=chapters.length);
 root.querySelectorAll('.studio-summary').forEach(node=>node.textContent=document.querySelector('#notes>.summary p')?.textContent||heading.querySelector('.subtitle')?.textContent||'');
 let screen='',drag=null,constrainWindows=()=>{};const positions=new Map();
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
  buildJournalMemos(root);
  const tags=new Map();shelf.entries.forEach(entry=>entry.tags.forEach(tag=>tags.set(tag,(tags.get(tag)||0)+1)));const tagHost=root.querySelector('.journal-tags');tags.forEach((count,tag)=>{const button=document.createElement('button'),label=document.createElement('span'),number=document.createElement('small');button.type='button';label.textContent='#  '+tag;number.textContent=count;button.append(label,number);button.addEventListener('click',()=>{root.querySelector('.shelf-search').value=tag;filterShelf(tag)});tagHost.append(button)});if(!tags.size)tagHost.hidden=true;
  shelf.entries.slice(0,4).forEach(entry=>{const link=card(entry);link.classList.add('recent-note');root.querySelector('.journal-recent-list').append(link)});
 }
 root.addEventListener('click',event=>{
  const button=event.target.closest('[data-studio-action]');if(button){event.preventDefault();const action=button.dataset.studioAction;if(['home','shelf','desktop'].includes(action)){show(action);return}if(action==='print')window.print();if(action==='export')document.querySelector('.obsidian-link')?.click()}
  const windowButton=event.target.closest('[data-window-action]');if(windowButton){const panel=windowButton.closest('[data-window]'),action=windowButton.dataset.windowAction;if(action==='minimize')panel.hidden=true;else if(action==='maximize'){const maximized=panel.classList.toggle('maximized');windowButton.setAttribute('aria-label',maximized?'还原笔记窗口':'最大化笔记窗口');windowButton.textContent=maximized?'▣':'□';if(!maximized)constrainWindows()}else show(style==='pixel'?'desktop':'home');updateTasks()}
  const restore=event.target.closest('[data-window-restore]');if(restore){const panel=root.querySelector('[data-window='+restore.dataset.windowRestore+']');panel.hidden=false;root.querySelectorAll('[data-window]').forEach(node=>node.style.zIndex=node===panel?'25':'8');updateTasks()}
 });
 function updateTasks(){root.querySelectorAll('[data-window-restore]').forEach(button=>button.setAttribute('aria-pressed',String(!root.querySelector('[data-window='+button.dataset.windowRestore+']').hidden)))}
 function key(event){if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();const input=root.querySelector('.shelf-search');input?.focus()}if(style==='pixel'&&event.key==='Escape'&&document.fullscreenElement)document.exitFullscreen().catch(()=>{})}
 document.addEventListener('keydown',key);sceneCleanups.push(()=>document.removeEventListener('keydown',key));
 if(style==='pixel'){
  const fullscreen=root.querySelector('[data-pixel-fullscreen]'),message=root.querySelector('.pixel-system-message'),clock=root.querySelector('.pixel-clock');
  function syncFullscreen(){const active=!!document.fullscreenElement;fullscreen.setAttribute('aria-pressed',String(active));fullscreen.setAttribute('aria-label',active?'退出全屏':'进入全屏');fullscreen.querySelector('span').textContent=active?'退出全屏':'全屏';fullscreen.title=active?'退出全屏（Esc）':'全屏显示桌面';}
  fullscreen.addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();message.hidden=true;syncFullscreen()}catch{message.textContent='当前浏览器未允许全屏，可使用窗口右上角的最大化。';message.hidden=false}});
  document.addEventListener('fullscreenchange',syncFullscreen);syncFullscreen();
  function tick(){const now=new Date();clock.textContent=now.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false});clock.dateTime=now.toISOString();clock.title=now.toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'})}tick();const timer=setInterval(tick,30000);
  sceneCleanups.push(()=>{clearInterval(timer);document.removeEventListener('fullscreenchange',syncFullscreen)});
  function applyWindowBox(panel,box){panel.classList.add('resized');Object.assign(panel.style,{position:'fixed',left:box.left+'px',top:box.top+'px',right:'auto',bottom:'auto',width:box.width+'px',height:box.height+'px'})}
  function resizePanel(panel,width,height,rect){const maxWidth=innerWidth-rect.left-8,maxHeight=innerHeight-rect.top-62,notes=panel.dataset.window==='notes';applyWindowBox(panel,{left:rect.left,top:rect.top,width:Math.max(Math.min(notes?480:240,maxWidth),Math.min(maxWidth,width)),height:Math.max(Math.min(notes?340:150,maxHeight),Math.min(maxHeight,height))})}
  function resizeFromHandle(panel,rect,dx,dy,direction){const notes=panel.dataset.window==='notes';applyWindowBox(panel,resizePixelWindow(rect,dx,dy,direction,{left:8,top:8,right:innerWidth-8,bottom:innerHeight-62},notes?480:240,notes?340:150))}
  constrainWindows=()=>{if(innerWidth<=700)return;root.querySelectorAll('[data-window].resized:not(.maximized)').forEach(panel=>{const rect=panel.getBoundingClientRect();if(!rect.width)return;const notes=panel.dataset.window==='notes',left=Math.max(8,Math.min(rect.left,innerWidth-(notes?480:240)-8)),top=Math.max(8,Math.min(rect.top,innerHeight-(notes?340:150)-62));panel.style.left=left+'px';panel.style.top=top+'px';resizePanel(panel,rect.width,rect.height,{left,top})})};
  window.addEventListener('resize',constrainWindows);sceneCleanups.push(()=>window.removeEventListener('resize',constrainWindows));
  root.querySelectorAll('[data-window]').forEach(panel=>Object.entries({nw:'左上角',n:'上边',ne:'右上角',e:'右边',se:'右下角',s:'下边',sw:'左下角',w:'左边'}).forEach(([direction,name])=>{const grip=document.createElement('button');grip.type='button';grip.className='pixel-resize-grip';grip.dataset.resize=direction;grip.setAttribute('aria-label',(panel.dataset.window==='notes'?'调整笔记窗口大小：':'调整目录窗口大小：')+name);grip.title=name+'：'+(direction.length===2?'等比例缩放':'单方向调整')+'；也可用方向键';panel.append(grip);grip.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)||panel.classList.contains('maximized'))return;event.preventDefault();event.stopPropagation();const step=event.shiftKey?40:16;resizeFromHandle(panel,panel.getBoundingClientRect(),event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0,event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0,direction)})}));
  root.addEventListener('pointerdown',event=>{const grip=event.target.closest('.pixel-resize-grip'),bar=event.target.closest('.pixel-titlebar'),handle=grip||bar;if(!handle||!grip&&event.target.closest('button')||event.button!==0||innerWidth<700)return;const panel=handle.closest('[data-window]');if(panel.classList.contains('maximized'))return;event.preventDefault();const rect=panel.getBoundingClientRect();drag={panel,id:event.pointerId,direction:grip?.dataset.resize,x:event.clientX,y:event.clientY,left:rect.left,top:rect.top,width:rect.width,height:rect.height};panel.style.position='fixed';panel.style.left=rect.left+'px';panel.style.top=rect.top+'px';panel.style.right='auto';panel.style.bottom='auto';panel.style.width=rect.width+'px';panel.style.zIndex='30';handle.setPointerCapture(event.pointerId)});
  root.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;if(drag.direction){resizeFromHandle(drag.panel,drag,event.clientX-drag.x,event.clientY-drag.y,drag.direction);return}drag.panel.style.left=Math.max(0,Math.min(innerWidth-180,drag.left+event.clientX-drag.x))+'px';drag.panel.style.top=Math.max(0,Math.min(innerHeight-90,drag.top+event.clientY-drag.y))+'px'});
  root.addEventListener('pointerup',()=>drag=null);root.addEventListener('pointercancel',()=>drag=null);updateTasks();
 }
 root.querySelector('.scene-reader-body')?.addEventListener('scroll',queueReading,{passive:true});
 root.querySelectorAll('[data-studio-action=export]').forEach(button=>button.hidden=!document.querySelector('.obsidian-link'));
 show(style==='pixel'?'desktop':'home');return {show,screen:()=>screen};
}
