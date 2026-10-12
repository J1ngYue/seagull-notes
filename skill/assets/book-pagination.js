// Move original note blocks into measured pages; restore them when leaving the book.
function paginateNotebookBook(spread,documents,options){
 const pages=[],homes=[],paragraphs=[],chapterPages=new Map(),starts=[],moved=new Set(),imageHeights=new Map();let current=null,contexts=new Map();
 const width=spread.clientWidth/(matchMedia('(max-width:700px)').matches?1:2),height=spread.clientHeight;
 function remember(node){if(moved.has(node))return;const marker=document.createComment('paged block home');node.before(marker);homes.push([node,marker]);moved.add(node)}
 function newPage(doc){
  const page=document.createElement('section');page.className='book-page folio-visible book-measure-page';page.id='book-page-'+(pages.length+1);page.dataset.bookPage=String(pages.length+1);page.dataset.chapter=String(doc.chapter);
  page.style.cssText='position:absolute;left:0;top:0;width:'+width+'px;height:'+height+'px;visibility:hidden';
  const body=document.createElement('div');body.className='book-page-body';page.append(body);
  const header=doc.header.cloneNode(true);header.removeAttribute('id');header.querySelectorAll('[id]').forEach(element=>element.removeAttribute('id'));
  if(pages.some(item=>item.document===doc)){const title=header.querySelector('h2')||header;title.append(document.createTextNode('（续）'))}body.append(header);
  const footer=document.createElement('footer');footer.className='book-page-footer';const number=document.createElement('span');number.className='book-page-number';number.textContent=String(pages.length+1);footer.append(number);page.append(footer);spread.append(page);
  current={page,body,footer,document:doc,blocks:0,start:null};contexts=new Map();pages.push(current);if(!chapterPages.has(doc.chapter))chapterPages.set(doc.chapter,pages.length-1);return current;
 }
 function available(){const css=getComputedStyle(current.page);return current.page.clientHeight-parseFloat(css.paddingTop)-parseFloat(css.paddingBottom)-58}
 function fits(){return current.body.scrollHeight<=available()+1}
 function target(block){
  if(!block.context)return current.body;
  if(!contexts.has(block.context)){const wrapper=block.wrapper();current.body.append(wrapper.outer);contexts.set(block.context,wrapper)}
  return contexts.get(block.context).target;
 }
 function append(block,node,offset=0){target(block).append(node);if(!current.start)current.start={node:block.origin||block.node,offset};current.blocks++;return node}
 function trial(block,node){const host=target(block);host.append(node);const result=fits();node.remove();if(!result&&block.context&&!host.childElementCount&&!host.textContent.trim()){contexts.get(block.context).outer.remove();contexts.delete(block.context)}return result}
 function plainWrapper(source){return ()=>{const wrapper=source.cloneNode(false);wrapper.removeAttribute('id');return {outer:wrapper,target:wrapper}}}
 function proseWrapper(source,inner){return ()=>{const prose=source.cloneNode(false);prose.removeAttribute('id');if(!inner)return {outer:prose,target:prose};const nested=inner.cloneNode(false);nested.removeAttribute('id');prose.append(nested);return {outer:prose,target:nested}}}
 function blocksOf(source,context=null,wrapper=null){
  const result=[];
  function add(node,group=context,factory=wrapper){result.push({node,origin:node,context:group,wrapper:factory})}
  if(source.matches('.prose')){
   Array.from(source.children).forEach(node=>{
    if(node.matches('ul,ol'))Array.from(node.children).forEach((item,index)=>add(item,node,()=>{const made=proseWrapper(source,node)();if(node.tagName==='OL')made.target.start=(Number(node.getAttribute('start'))||1)+index;return made}));
    else if(node.matches('table')){
     const rows=Array.from(node.querySelectorAll('tbody>tr'));if(!rows.length){add(node,source,proseWrapper(source));return}
     rows.forEach(row=>add(row,node,()=>{const prose=source.cloneNode(false),table=node.cloneNode(false),body=document.createElement('tbody');prose.removeAttribute('id');table.removeAttribute('id');Array.from(node.children).filter(child=>child.matches('caption,colgroup,thead')).forEach(child=>{const copy=child.cloneNode(true);copy.querySelectorAll('.arithmatex').forEach(math=>delete math.dataset.copyBound);table.append(copy)});table.append(body);prose.append(table);return {outer:prose,target:body}}));
    }else add(node,source,proseWrapper(source));
   });
  }else if(source.matches('.takeaways,.review-deck,.extension-deck')){
   Array.from(source.children).filter(node=>!node.matches('.label,h3')).forEach(node=>{
    if(node.matches('details')&&node.querySelector('.prose')){const answer=node.querySelector('.prose');Array.from(answer.children).forEach(part=>add(part,node,()=>{const outer=source.cloneNode(false);Array.from(source.children).filter(child=>child.matches('.label,h3')).forEach(child=>outer.append(child.cloneNode(true)));const question=document.createElement('h4');question.className='book-question';question.textContent=node.querySelector('summary').textContent;const prose=answer.cloneNode(false);outer.append(question,prose);return {outer,target:prose}}))}
    else add(node,source,()=>{const outer=source.cloneNode(false);Array.from(source.children).filter(child=>child.matches('.label,h3')).forEach(child=>outer.append(child.cloneNode(true)));return {outer,target:outer}});
   });
  }else if(source.matches('.source-list'))Array.from(source.children).forEach(node=>add(node,source,plainWrapper(source)));
  else if(source.matches('.study-widgets'))Array.from(source.children).forEach(node=>result.push(...blocksOf(node)));
  else add(source);
  return result;
 }
 function textPositions(root,protectInline){
  const points=[];
  function walk(node){
   if(node.nodeType===Node.TEXT_NODE){if(protectInline){let offset=0;for(const letter of node.textContent){offset+=letter.length;points.push({node,offset})}}else for(let offset=1;offset<=node.textContent.length;offset++)points.push({node,offset})}
   else if(node.nodeType===Node.ELEMENT_NODE){
    if(protectInline&&node!==root&&node.matches('.arithmatex,code,a,img,svg')){const index=Array.from(node.parentNode.childNodes).indexOf(node);points.push({node:node.parentNode,offset:index+1})}
    else Array.from(node.childNodes).forEach(walk);
   }
  }walk(root);return points;
 }
 function bestPrefix(block,source,points){
  let low=1,high=points.length,best=0;
  while(low<=high){const middle=Math.floor((low+high)/2),range=document.createRange();range.setStart(source,0);range.setEnd(points[middle-1].node,points[middle-1].offset);const copy=source.cloneNode(false);copy.removeAttribute('id');copy.append(range.cloneContents());if(trial(block,copy)){best=middle;low=middle+1}else high=middle-1}
  return best;
 }
 function splitParagraph(block,doc){
  const source=block.node,parts=[];paragraphs.push([source,parts]);let consumed=0;
  while(source.childNodes.length){
   const points=textPositions(source,true);if(!points.length)break;
   let count=bestPrefix(block,source,points);
   if(!count){if(current.blocks){newPage(doc);continue}count=1}
   if(count<points.length){for(let boundary=count;boundary>Math.max(0,count-40);boundary--){const point=points[boundary-1];if(point.node.nodeType===Node.TEXT_NODE&&/[。！？；\n]/.test(point.node.textContent[point.offset-1])){count=boundary;break}}}
   const range=document.createRange();range.setStart(source,0);range.setEnd(points[count-1].node,points[count-1].offset);
   const part=source.cloneNode(false);part.removeAttribute('id');part.append(range.extractContents());parts.push(part);append(block,part,consumed);consumed+=count;
   if(source.textContent.trim())newPage(doc);else{if(source.childNodes.length){const rest=source.cloneNode(false);rest.append(...Array.from(source.childNodes));parts.push(rest);append(block,rest,consumed)}break}
  }
 }
 function codePart(source,start,end){
  const original=source.querySelector('code'),positions=textPositions(original,false),range=document.createRange();range.setStart(original,0);
  if(start)range.setStart(positions[start-1].node,positions[start-1].offset);if(end)range.setEnd(positions[end-1].node,positions[end-1].offset);else range.setEnd(original,0);
  const piece=source.cloneNode(true);piece.removeAttribute('id');piece.querySelectorAll('[id]').forEach(element=>element.removeAttribute('id'));piece.querySelector('code').replaceChildren(range.cloneContents());return piece;
 }
 function bindCodePart(piece,source){
  const copy=piece.querySelector('.copy-code'),wrap=piece.querySelector('.wrap-code'),full=source.querySelector('code').textContent;copy.querySelector('span').textContent='复制整段';copy.setAttribute('aria-label',source.querySelector('.copy-code').getAttribute('aria-label')+'（完整）');
  copy.addEventListener('click',async()=>{if(await copyText(full,'已复制完整代码','复制失败，请在 Markdown 中复制')){copy.querySelector('span').textContent='已复制';setTimeout(()=>{copy.querySelector('span').textContent='复制整段'},1800)}});
  wrap.addEventListener('click',()=>{source.querySelector('.wrap-code').click();options.reflow()});
 }
 function splitCode(block,doc){
  const source=block.node,full=source.querySelector('code').textContent,ends=[];let position=0;
  full.split(/(?<=\n)/).filter(line=>line.length).forEach(line=>{position+=line.length;ends.push(position)});let first=0;
  while(first<ends.length){
   let low=first+1,high=ends.length,best=first;
   while(low<=high){const middle=Math.floor((low+high)/2),piece=codePart(source,first?ends[first-1]:0,ends[middle-1]);if(trial(block,piece)){best=middle;low=middle+1}else high=middle-1}
   if(best===first){if(current.blocks){newPage(doc);continue}best=first+1}
   const piece=codePart(source,first?ends[first-1]:0,ends[best-1]);bindCodePart(piece,source);append(block,piece,first?ends[first-1]:0);first=best;if(first<ends.length)newPage(doc);
  }
 }
 function sizeImage(node){const image=node.matches('figure')?node.querySelector('img'):null;if(image){if(!imageHeights.has(image))imageHeights.set(image,image.style.maxHeight);image.style.maxHeight=Math.max(80,available()-current.body.scrollHeight-48)+'px'}}
 documents.forEach(doc=>{
  newPage(doc);const blocks=doc.sources.flatMap(source=>blocksOf(source));
  blocks.forEach(block=>{
   const node=block.node;sizeImage(node);const copy=node.cloneNode(true);
   if(!trial(block,copy)&&current.blocks)newPage(doc);
   sizeImage(node);
   if(trial(block,node.cloneNode(true))){remember(node);append(block,node)}
   else if(node.tagName==='P')splitParagraph(block,doc);
   else if(node.matches('.code-block'))splitCode(block,doc);
   else{remember(node);append(block,node);if(!fits()){node.classList.add('book-atomic-overflow');node.style.maxHeight=Math.max(90,available()-current.body.scrollHeight+node.getBoundingClientRect().height)+'px'}}
  });
  if(doc.footer){remember(doc.footer);current.footer.prepend(doc.footer)}
 });
 pages.forEach((item,index)=>{item.page.classList.remove('book-measure-page','folio-visible');item.page.removeAttribute('style');starts.push(item.start);item.page.dataset.bookPage=String(index+1);options.bindMath(item.page)});
 return {pages:pages.map(item=>item.page),chapterPages,starts,restore(){
  paragraphs.forEach(([source,parts])=>source.replaceChildren(...parts.flatMap(part=>Array.from(part.childNodes)),...Array.from(source.childNodes)));
  homes.forEach(([node,marker])=>{node.classList.remove('book-atomic-overflow');node.style.removeProperty('max-height');marker.after(node);marker.remove()});pages.forEach(item=>item.page.remove());
  imageHeights.forEach((value,image)=>{image.style.maxHeight=value});
 }};
}
