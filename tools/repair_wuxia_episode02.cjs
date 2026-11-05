// Run from the repository root after rebuilding the episode-02 package.
const fs=require('fs'),load=require('../auth-web/tests/load-ts-module.cjs');process.chdir('auth-web');const {wuxiaGraphicIsSafe}=load('lib/stdWuxiaGraphic.ts');const {wuxiaBubbleContour}=load('lib/stdWuxiaBubble.ts');process.chdir('..');
const dir='output/wuxia-series-rebuild/episode-02/direction',pkg=JSON.parse(fs.readFileSync(dir+'/ae-scene-package.json')),faces=JSON.parse(fs.readFileSync('docs/wuxia-handoff/episode-02/direction/face-protection.json'));
const shout=new Set([2,11,13,14,21]),gentle=new Set([10,15,22]);const changed=[];
for(const scene of pkg.scenes){const n=+scene.scene_id.slice(-2);let total=scene.blocks.reduce((a,b)=>a+b.text.length,0);
 for(const state of scene.states){const key=state.asset_id.slice(5,7)+'_'+state.asset_id.slice(-2);if(!faces.boxes[key])throw Error('missing face review '+key);state.face_exclusion_boxes=faces.boxes[key];state.static_crop=null;state.face_review=faces.basis}
 for(const [index,g]of scene.graphics.entries()){
  const b=scene.blocks.find(b=>b.block_id===(g.block_id||g.voice_binding.block_id));if(!b)throw Error('block missing');
  const anchor=g.voice_binding.exact_anchor||g.text,offset=b.text.indexOf(anchor);if(offset<0)throw Error('anchor missing');
  const span=b.preview_end-b.preview_start;g.preview_start=b.preview_start+span*offset/b.text.length;g.preview_end=b.preview_start+span*(offset+anchor.length)/b.text.length;
  // Use the same exact sentence/voice interval for graphics and dialogue.
  g.voice_binding={...g.voice_binding,exact_anchor:anchor,block_id:b.block_id};
  if(g.kind==='speech_bubble'){g.bubble_style=shout.has(n)?'shout':n===3?'whisper':gentle.has(n)?'rounded':'dialogue';g.style={...g.style,size:46,scale_peak:100};}
  const state=scene.states.find(s=>s.asset_id===g.state_asset_id),boxes=state.face_exclusion_boxes;
  if(n===22&&g.kind==='speech_bubble')g.layout.center=[.41,.80];
  if(n===21&&g.kind==='sfx'){g.layout.center=[.11,.14];g.layout.size=[.14,.14]}
  const original=JSON.parse(JSON.stringify(g.layout));let candidates=[];
  // Preserve the authored position whenever it is actually safe, otherwise use inspected negative space.
  const centers=[original.center];for(let y=.12;y<=.88;y+=.04)for(let x=.13;x<=.87;x+=.04)centers.push([+x.toFixed(3),+y.toFixed(3)]);
  const sizes=g.kind==='speech_bubble'?[[Math.max(.32,original.size[0]),Math.max(.20,original.size[1])],[.38,.23],[.32,.25]]:[original.size];
  for(const size of sizes)for(const c of centers){const q={...g,layout:{...original,center:c,size}};if(wuxiaGraphicIsSafe(q,boxes))candidates.push({q,score:Math.hypot((c[0]-original.center[0])*1.3,c[1]-original.center[1])+Math.abs(size[0]-original.size[0])*.2});}
  candidates.sort((a,b)=>a.score-b.score);if(!candidates.length)throw Error('No safe space '+scene.scene_id+' '+index);
  g.layout=candidates[0].q.layout;g.layout.placement_review='source_head_boxes_and_full_contour_checked_2026-11-05';g.layout.protected_boxes=boxes;
  if(!wuxiaGraphicIsSafe(g,boxes))throw Error('unsafe final');
  if(g.kind==='speech_bubble')g.layout.body_contour=wuxiaBubbleContour(g.layout.center.map((v,i)=>v*(i?1080:1920)),g.layout.size.map((v,i)=>v*(i?1080:1920)),g.layout.offscreen_speaker?undefined:g.layout.tail?.map((v,i)=>v*(i?1080:1920)),g.bubble_style).points;
  changed.push({scene:scene.scene_id,text:g.text,style:g.bubble_style||g.kind,layout:g.layout,old:original,start:g.preview_start,end:g.preview_end});
 }
}
pkg.graphics_revision='episode02-face-style-timing-2026-11-05';pkg.timing='Exact frozen block/sentence anchors; preview fractions remain provisional until bound to saved voice-row intervals.';
fs.writeFileSync(dir+'/ae-scene-package.json',JSON.stringify(pkg,null,2));fs.writeFileSync('docs/wuxia-handoff/episode-02/direction/ae-scene-package.json',JSON.stringify(pkg,null,2));
fs.writeFileSync('output/wuxia-episode02-audit/repair-receipt.json',JSON.stringify(changed,null,2));console.log('safe graphics',changed.length,'moved',changed.filter(x=>JSON.stringify(x.old.center)!==JSON.stringify(x.layout.center)).length);
