// Distinct reading spaces reuse the existing heading, chapters and format controls.
const themedModes=['whale','anime','cyber'],themeHeading=document.querySelector('.note-head'),themeHeadingHome=document.createComment('original note heading');
themeHeading.before(themeHeadingHome);
const themeStage=document.createElement('section');themeStage.className='theme-stage';themeStage.hidden=true;themeStage.setAttribute('aria-label','主题阅读空间');
themeStage.innerHTML='<div class="theme-stage-copy"><div class="theme-stage-heading"></div><div class="theme-stage-actions"><button type="button" class="theme-read">开始阅读 <span aria-hidden="true">↗</span></button><button type="button" class="theme-map">查看思维导图</button></div></div><div class="theme-cast" aria-hidden="true"><div class="theme-cast-orbit"></div><div class="theme-cast-art"></div><div class="theme-cast-caption"></div></div><div class="theme-stage-meter"><span class="theme-count"></span><span class="theme-position">准备开始阅读</span><span class="theme-mastery"></span><progress class="theme-progress" value="0" max="100" aria-label="主题阅读进度"></progress></div>';
themeHeading.parentElement.prepend(themeStage);
const themeNames={whale:['肥鱼自习室','和大肥鱼一起，把知识吃透。'],anime:['次元放映厅','翻开下一幕，记住每个灵感。'],cyber:['霓虹矩阵','KNOWLEDGE SYSTEM · ONLINE']};
function updateThemeMeters(index){
 const total=chapters.length,position=Number.isInteger(index)&&index>=0?Math.min(index+1,total):Math.max(0,currentChapter+1);
 themeStage.querySelector('.theme-count').textContent=(document.body.dataset.style==='cyber'?'INDEX // ':'学习章节 · ')+String(total).padStart(2,'0');
 themeStage.querySelector('.theme-position').textContent=position?'正在阅读 '+String(position).padStart(2,'0')+' / '+String(total).padStart(2,'0'):'准备开始阅读';
 themeStage.querySelector('.theme-mastery').textContent='已掌握 '+document.getElementById('mastery-percent').textContent;
 themeStage.querySelector('.theme-progress').value=total?Math.round(position/total*100):0;
}
function applyThemeScene(style){
 const enabled=themedModes.includes(style);themeStage.hidden=!enabled;
 document.querySelector('.sidebar>.label').textContent=style==='cyber'?'MATRIX // INDEX':style==='anime'?'EPISODE INDEX':style==='whale'?'STUDY ROOM':'THE READING ROOM';
 if(enabled){themeStage.setAttribute('aria-label',themeNames[style][0]+'阅读空间');themeStage.querySelector('.theme-stage-heading').append(themeHeading);themeStage.querySelector('.theme-cast-caption').textContent=themeNames[style][1];themeStage.querySelector('.theme-read').firstChild.textContent=style==='cyber'?'进入知识矩阵 ':style==='anime'?'开始这一幕 ':'和肥鱼一起读 ';updateThemeMeters()}
 else themeHeadingHome.after(themeHeading);
}
themeStage.querySelector('.theme-read').addEventListener('click',()=>{activate(document.getElementById('tab-notes'));goToChapter(Math.max(0,currentChapter))});
themeStage.querySelector('.theme-map').addEventListener('click',()=>activate(document.getElementById('tab-map')));
document.addEventListener('seagull:position',event=>updateThemeMeters(event.detail));
document.querySelectorAll('.chapter,.theme-stage').forEach(surface=>{let frame=0,x=50,y=0;surface.addEventListener('pointermove',event=>{if(document.body.dataset.style!=='cyber'||matchMedia('(prefers-reduced-motion: reduce)').matches)return;const box=surface.getBoundingClientRect();x=(event.clientX-box.left)/box.width*100;y=(event.clientY-box.top)/box.height*100;if(!frame)frame=requestAnimationFrame(()=>{frame=0;surface.style.setProperty('--spot-x',x+'%');surface.style.setProperty('--spot-y',y+'%')})},{passive:true})});
