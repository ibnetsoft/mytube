const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript');
function harness(hidden = false) {
    const timers = new Map(), listeners = new Map(); let id = 0;
    const document = { hidden, addEventListener: (k,v) => listeners.set(k,v), removeEventListener: k => listeners.delete(k) };
    const exports = {};
    new Function('exports','document','setTimeout','clearTimeout',ts.transpileModule(fs.readFileSync('lib/stdVisiblePolling.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText)(exports,document,
        (fn,ms)=>{timers.set(++id,{fn,ms});return id}, key=>timers.delete(key));
    return { start:exports.startVisiblePolling, timers, document, listeners,
        tick(ms) { const match=[...timers].find(([,t])=>t.ms===ms); assert(match,`Missing ${ms}ms timer`);timers.delete(match[0]);match[1].fn() },
        visibility(hidden) {document.hidden=hidden;listeners.get('visibilitychange')?.()} };
}
const flush = async () => {for(let i=0;i<6;i++) await Promise.resolve()};
test('slow requests serialize, hidden tabs stop, and visible tabs resume once',async()=>{
    const h=harness();let calls=0,finish,signal;
    const stop=h.start(s=>{calls++;signal=s;return new Promise(r=>finish=r)},10000);
    assert.equal(calls,1);assert.equal(h.timers.size,1,'Only request timeout exists while pending');
    h.visibility(true);h.visibility(false);assert.equal(calls,1);
    finish();await flush();h.tick(10000);assert.equal(calls,2);
    h.visibility(true);finish();await flush();assert.equal(h.timers.size,0);
    h.visibility(false);assert.equal(calls,3);stop();assert(signal.aborted);
    finish();await flush();assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);
});
test('errors back off to two minutes and successful reads reset the interval',async()=>{
    const h=harness();let fail=true;
    const stop=h.start(async()=>{if(fail)throw Error('offline')},15000);
    await flush();h.tick(30000);await flush();h.tick(60000);await flush();h.tick(120000);await flush();
    fail=false;h.tick(120000);await flush();h.tick(15000);await flush();stop();
});
test('hidden startup does not query, idle jobs use a slower interval, timeout aborts',async()=>{
    const h=harness(true);let calls=0,signal;
    const stop=h.start(async()=>{calls++;return 60000},15000);
    assert.equal(calls,0);h.visibility(false);await flush();h.tick(60000);await flush();assert.equal(calls,2);stop();
    const slow=harness();let finish;
    const end=slow.start(s=>{signal=s;return new Promise(r=>finish=r)},15000);
    slow.tick(20000);assert(signal.aborted);end();finish();await flush();assert.equal(slow.timers.size,0);
});
