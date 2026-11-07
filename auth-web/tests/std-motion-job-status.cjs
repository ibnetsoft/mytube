const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {motionOutputStatus}=load('lib/stdMotionJobStatus.ts');
test('unsupported worker passthrough is never counted as a native output',()=>{
 const s=motionOutputStatus({state:'awaiting_worker_update',results:[{source_passthrough:'unchanged_source_passthrough/v1'}]});
 assert.equal(s.reviewed_scenes,0);assert.equal(s.native_wuxia,true);assert.match(s.error,/워커 업데이트/);
});
test('native count requires both source timeline and Adobe render evidence',()=>{
 const good={ambient_renderer:'ambient_loop/v1',adobe_flat_renderer:'adobe_flat_scene/v1'};
 const s=motionOutputStatus({state:'processing',input_worker_contract:'wuxia_native_timeline/v3',results:[good,{...good,source_passthrough:'unchanged_source_passthrough/v1'},{ambient_renderer:'ambient_loop/v1'}]});
 assert.equal(s.reviewed_scenes,1);
});
test('other production status retains its existing results and error',()=>{
 const s=motionOutputStatus({state:'processing',results:[{},{}],error:'existing error'});
 assert.equal(s.reviewed_scenes,2);assert.equal(s.native_wuxia,false);assert.equal(s.error,'existing error');
});
