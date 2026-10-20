const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const load=require('./load-ts.cjs');
const {assertPreparationFinished,assertPreparedMouthGeometry}=load(path.join(__dirname,'../lib/stdWorkflowBoundary.ts'));
test('submission waits for image/geometry/direction preparation',()=>{
 for(const kind of ['ae_scene_preparation','ae_speaker_coordinates','region_layer_package','motion_preview']){
  assert.throws(()=>assertPreparationFinished([{metadata:{kind,state:'processing',input:{task:'direction'}}}]));
  assert.doesNotThrow(()=>assertPreparationFinished([{metadata:{kind,state:'ready',input:{task:'direction'}}}]));
 }
});
test('final speaker assignments must match prepared coordinates',()=>{
 const input={scenes:[{number:1}],subtitles:[{scene_number:1,kind:'dialogue',speaker:'A'}]};
 assert.throws(()=>assertPreparedMouthGeometry(input));
 input.scenes[0].speaker_regions={speakers:[{speaker:'A'}]};assert.doesNotThrow(()=>assertPreparedMouthGeometry(input));
 input.subtitles[0].speaker='B';assert.throws(()=>assertPreparedMouthGeometry(input));
});
