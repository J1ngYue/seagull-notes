// Geometry regression: all edges and corners, with fixed opposite anchors.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const resize=vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../skill/assets/studios.js'),'utf8')+'\nresizePixelWindow;');
const box={left:200,top:180,width:600,height:400};
const bounds={left:8,top:8,right:1592,bottom:938};
const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
for(const direction of ['n','e','s','w']){
 const next=resize(box,direction==='w'?-90:90,direction==='n'?-60:60,direction,bounds,240,150);
 if(direction==='e'||direction==='w'){
  near(next.width,690);near(next.height,box.height);near(next.top,box.top);
  near(direction==='w'?next.left+next.width:next.left,direction==='w'?box.left+box.width:box.left);
 }else{
  near(next.height,460);near(next.width,box.width);near(next.left,box.left);
  near(direction==='n'?next.top+next.height:next.top,direction==='n'?box.top+box.height:box.top);
 }
}
for(const direction of ['nw','ne','sw','se']){
 const next=resize(box,direction.includes('w')?-90:90,direction.includes('n')?-60:60,direction,bounds,240,150);
 near(next.width,690);near(next.height,460);
 for(const dx of [-2000,-100,0,50,2000])for(const dy of [-2000,-100,0,50,2000]){
  const result=resize(box,dx,dy,direction,bounds,240,150);
  near(result.width/result.height,box.width/box.height);
  near(direction.includes('w')?result.left+result.width:result.left,direction.includes('w')?box.left+box.width:box.left);
  near(direction.includes('n')?result.top+result.height:result.top,direction.includes('n')?box.top+box.height:box.top);
  assert.ok(result.left>=bounds.left-1e-8&&result.top>=bounds.top-1e-8);
  assert.ok(result.left+result.width<=bounds.right+1e-8&&result.top+result.height<=bounds.bottom+1e-8);
  assert.ok(result.width>=240-1e-8&&result.height>=150-1e-8);
 }
}
for(const direction of ['n','e','s','w'])for(const delta of [-2000,2000]){
 const result=resize(box,delta,delta,direction,bounds,240,150);
 assert.ok(result.left>=bounds.left&&result.top>=bounds.top);
 assert.ok(result.left+result.width<=bounds.right&&result.top+result.height<=bounds.bottom);
 assert.ok(result.width>=240&&result.height>=150);
}
process.stdout.write('Four proportional corners and four independent edges preserve anchors, minimum sizes and desktop bounds.\n');
