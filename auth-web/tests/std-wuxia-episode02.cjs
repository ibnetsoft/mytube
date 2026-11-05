const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),load=require('./load-ts-module.cjs');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts'),{wuxiaGraphicIsSafe,wuxiaGraphicPose,wuxiaFontFamily}=load('lib/stdWuxiaGraphic.ts'),{wuxiaBubbleContour}=load('lib/stdWuxiaBubble.ts');
const pkg=JSON.parse(fs.readFileSync('../docs/wuxia-handoff/episode-02/direction/ae-scene-package.json'));
test('all 35 episode-2 graphics protect reviewed heads across their full outline and maximum scale',()=>{
 let count=0;for(const s of pkg.scenes)for(const g of s.graphics){const state=s.states.find(a=>a.asset_id===g.state_asset_id);assert.ok(wuxiaGraphicIsSafe(g,state.face_exclusion_boxes),s.scene_id+' '+g.text);count++}assert.equal(count,35)
});
test('all 21 bubbles follow their split voice sentence through its last row',()=>{
 let count=0;for(const [index,s]of pkg.scenes.entries()){
  let offset=0;const rows=[];for(const b of s.blocks)for(const text of b.text.match(/.{1,8}/gu)||[]){rows.push({scene_number:index+1,text,start_num:offset,end_num:++offset})}
  for(const g of s.graphics.filter(g=>g.kind==='speech_bubble')){
   const b=s.blocks.find(b=>b.block_id===g.block_id),prefix=s.blocks.slice(0,s.blocks.indexOf(b)).reduce((n,b)=>n+Math.ceil(b.text.length/8),0),last=prefix+Math.ceil(b.text.length/8)-.05;
   const frame=wuxiaSceneFrame({structure:{wuxia_ae_package:pkg}},index+1,rows,last);assert.ok(frame.graphics.some(x=>x.block_id===g.block_id),s.scene_id+' '+g.text);assert.equal(frame.state.asset_id,g.state_asset_id);count++
  }
 }assert.equal(count,21)
});
test('preset contours, selected fonts and typography motion preserve their distinctions',()=>{
 const paths=['dialogue','rounded','shout','whisper','thought','reaction','narration','electronic'].map(s=>wuxiaBubbleContour([960,200],[650,240],[1400,500],s).path);
 assert.equal(new Set(paths).size,7); // Whisper shares the dialogue outline, with a dashed stroke.
 assert.ok(pkg.scenes.flatMap(s=>s.graphics).some(g=>g.bubble_style==='shout'));assert.ok(pkg.scenes.flatMap(s=>s.graphics).some(g=>g.bubble_style==='whisper'));
 assert.equal(wuxiaFontFamily('DoHyeon-Regular'),'Do Hyeon');assert.equal(wuxiaFontFamily('BlackHanSans-Regular'),'Black Han Sans');
 const g={style:{rotation:-8,scale_peak:116}};assert.equal(wuxiaGraphicPose(g,.01).rotation,-8);assert.ok(wuxiaGraphicPose(g,.01).scale>wuxiaGraphicPose(g,.5).scale)
});
test('paused dialogue remains readable at the voice-row start while playback preserves its entry effect',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),{StdWuxiaGraphics}=load('components/StdWuxiaScenePreview.tsx');
 const g={...pkg.scenes[0].graphics[0],progress:0};
 assert.match(renderToStaticMarkup(React.createElement(StdWuxiaGraphics,{graphics:[g],animate:false})),/opacity="1"/);
 assert.match(renderToStaticMarkup(React.createElement(StdWuxiaGraphics,{graphics:[g],animate:true})),/opacity="0"/);
});
