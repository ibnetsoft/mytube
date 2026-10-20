const assert=require('node:assert/strict'),path=require('node:path'),load=require('./load-ts.cjs');
const D=load(path.resolve('lib/stdWebtoonDirection.ts')),M=load(path.resolve('lib/stdMotionStudio.ts'));
const cue={id:'reveal',start:.25,end:.75,kind:'reveal',target:'face',amount:1},pose={scale:1,x:.5,opacity:100};
assert.equal(D.directionPose(pose,[cue],'face',0).opacity,0);assert.equal(D.directionPose(pose,[cue],'face',.5).opacity,50);assert.equal(D.directionPose(pose,[cue],'face',1).opacity,100);assert.equal(D.directionPose(pose,[cue],'camera',0).opacity,100);
assert.throws(()=>D.normalizeDirectionCues([cue,cue]));assert.throws(()=>D.normalizeDirectionCues([{...cue,end:.1}]));
assert.throws(()=>D.normalizeDirectionCues([cue,{...cue,id:'other'}]));assert.throws(()=>D.validateDirectionTargets([cue],['body']));D.validateDirectionTargets([cue],['face']);
const shots=D.sliceMotionShots([{start:0,end:2,motionRange:[.2,.8],videoRange:[2,8]},{start:2,end:4,motionRange:[0,1]}],1,3);assert.deepEqual(shots.map(s=>[s.start,s.end]),[[0,1],[1,2]]);assert.deepEqual(shots[0].motionRange,[.5,.8]);assert.deepEqual(shots[0].videoRange,[5,8]);assert.deepEqual(shots[1].motionRange,[0,.5]);assert.deepEqual(D.boundaryWindow(2,4),{start:.5,end:3.5});assert.throws(()=>D.sliceMotionShots([],0,1));
const draft=M.normalizeMotionDraft({version:1,enabled:true,aspect:'16:9',fps:24,scenes:{1:{...M.motionScene(),cues:[cue]}}});assert.deepEqual(draft.scenes[1].cues,[cue]);console.log('PASS direction cue isolation, bounded ranges, persisted settings and partial source mapping');
