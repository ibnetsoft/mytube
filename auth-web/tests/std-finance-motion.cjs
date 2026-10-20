const assert=require('node:assert/strict'),path=require('node:path'),load=require('./load-ts.cjs');
const f=load(path.resolve('lib/stdFinanceMotion.ts')),m=load(path.resolve('lib/stdMotionStudio.ts'));
const config=f.financeMotion();assert.equal(f.financeFrame(config,1).pnl,-500);
const stopped=f.financeFrame({...config,mode:'liquidation',change:-20},1);assert.equal(stopped.stopped,true);assert.equal(stopped.equity,500);assert.equal(stopped.change,-5);
assert.equal(f.financeFrame({...config,change:2},1).pnl,200);
for(const bad of [NaN,Infinity,0,-1])assert.throws(()=>f.normalizeFinanceMotion({...config,capital:bad}));
const draft=m.normalizeMotionDraft({version:1,enabled:true,aspect:'16:9',fps:24,scenes:{1:{...m.motionScene(),finance:config}},web:{mode:'web',inserts:{}}});assert.deepEqual(draft.scenes[1].finance,config);
console.log('PASS FX gain/loss, stop-out, validation and saved motion roundtrip');
