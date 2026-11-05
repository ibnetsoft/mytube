const fs=require('fs'),path=require('path');const D=__dirname,P=path.dirname(D),ROOT=path.resolve(P,'../../..');
const ts=require(require.resolve('typescript',{paths:[path.join(ROOT,'auth-web/node_modules')]}));require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,f);
const {wuxiaGraphicIsSafe,wuxiaTextLines}=require(path.join(ROOT,'auth-web/lib/stdWuxiaGraphic.ts'));const {wuxiaBubbleContour}=require(path.join(ROOT,'auth-web/lib/stdWuxiaBubble.ts'));
function segmentHitsBox(a,b,r){let lo=0,hi=1;for(let axis=0;axis<2;axis++){const d=b[axis]-a[axis];if(Math.abs(d)<1e-9){if(a[axis]<r[axis]||a[axis]>r[axis+2])return false;}else{let p=(r[axis]-a[axis])/d,q=(r[axis+2]-a[axis])/d;if(p>q)[p,q]=[q,p];lo=Math.max(lo,p);hi=Math.min(hi,q);if(lo>hi)return false;}}return true;}
function strictSafe(g,boxes){if(!wuxiaGraphicIsSafe(g,boxes))return false;if(g.kind!=='speech_bubble'||g.layout.offscreen_speaker||!g.layout.tail)return true;const l=g.layout,shape=wuxiaBubbleContour(l.center.map((v,i)=>v*(i?1080:1920)),l.size.map((v,i)=>v*(i?1080:1920)),l.tail.map((v,i)=>v*(i?1080:1920)),g.bubble_style);if(!shape.tip)return true;const points=shape.points;return !boxes.some(b=>{const r=b.map((v,i)=>v*(i%2?1080:1920)+(i<2?-8:8));return segmentHitsBox(points.at(-2),points.at(-1),r)||segmentHitsBox(points.at(-1),points[0],r);});}
const pkg=JSON.parse(fs.readFileSync(path.join(D,'ae-scene-package.json')));let count=0;
for(const sc of pkg.scenes){for(const g of sc.graphics){const state=sc.states.find(x=>x.asset_id===g.state_asset_id),boxes=state.face_exclusion_boxes,anchor=state.speaker_mouths?.[g.speaker];let best=null;const original=g.style.size;
 for(const size of g.kind==='speech_bubble'?[38,36,34,32]:[original,Math.round(original*.9),Math.round(original*.8)]){
  g.style.size=size;
  for(const width of g.kind==='speech_bubble'?[.3,.36,.42,.48,.54,.6,.68,.75]:[.24,.3,.36,.44,.52,.62,.72]){
   const lines=wuxiaTextLines(g.text,width*1920-(g.kind==='speech_bubble'?100:24),size);const height=Math.max(g.kind==='speech_bubble'?.16:.09,(lines.length*size*1.18+(g.kind==='speech_bubble'?88:24))/1080);if(height>.6)continue;
   for(let y=.06+height/2;y<.95-height/2;y+=.035)for(let x=.03+width/2;x<.97-width/2;x+=.04){
    g.layout={center:[x,y],size:[width,height],offscreen_speaker:!anchor,protected_boxes:boxes,...(anchor?{tail:anchor}:{}),placement_review:'actual_source_head_boxes_and_full_unified_contour_checked'};
    if(!strictSafe(g,boxes))continue;
    const score=(original-size)*.04+y*.3+width*.06+(anchor?Math.hypot(x-anchor[0],y-anchor[1])*.18:0);if(!best||score<best.score)best={score,layout:structuredClone(g.layout),size};
   }
  }
  if(best)break;
 }
 if(!best)throw Error('No head-safe readable layout '+sc.scene_id+' '+g.text);g.layout=best.layout;g.style.size=best.size;
 if(g.kind==='speech_bubble'){const l=g.layout;const shape=wuxiaBubbleContour(l.center.map((v,i)=>v*(i?1080:1920)),l.size.map((v,i)=>v*(i?1080:1920)),!l.offscreen_speaker&&l.tail?l.tail.map((v,i)=>v*(i?1080:1920)):undefined,g.bubble_style);l.body_contour=shape.points;l.tail_length_px=shape.tailLength;}
 if(!strictSafe(g,boxes))throw Error('Unsafe final graphic');count++;
 }}
fs.writeFileSync(path.join(D,'ae-scene-package.json'),JSON.stringify(pkg,null,2));fs.writeFileSync(path.join(D,'graphic-safety-check.json'),JSON.stringify({graphics:count,unsafe:0,coordinate_system:'1920x1080 normalized head boxes',checks:['body bounds including peak scale and rotation','full unified tail contour vertices AND tail-segment intersections vs all heads','maximum tail length54px with64px speaker clearance','frame bounds','font wrapping'],all_text_editable:true,narration_caption_count:0},null,2));console.log(JSON.stringify({graphics:count,unsafe:0}));
