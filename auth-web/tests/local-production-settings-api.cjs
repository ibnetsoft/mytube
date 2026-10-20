const test=require('node:test'),assert=require('node:assert/strict');
const {main}=require('../../scripts/local_worker_settings.cjs');
const id='e9233112-f0d7-4b35-91bf-2f892844eb30';
function fixture(changes={}) {
 const project={id,title:'fixture',employee_email:'fixture@example.invalid',status:'in_progress',submitted_at:null,updated_at:'2026-10-20T00:00:00Z',project_payload:{subtitles:[{text:'keep'}],render_settings:{volume:.2}},...changes};let written;
 const db={from(table){const query={select(){return query},eq(){return query},is(){return query},update(value){written=value;return query},async maybeSingle(){return {data:written?{updated_at:'new-version'}:project,error:null}}};return query}};
 return {project,db,get written(){return written}};
}
const motion={version:1,enabled:true,aspect:'16:9',fps:24,scenes:{},automation:{mode:'ae_only',max_ai_clips:1,max_ai_seconds:5}};
test('native settings preserve subtitles and other render settings',async()=>{const f=fixture();const r=await main({worker_role:'preparation',path:`/api/local/projects/${id}/settings`,method:'POST',body:{version:f.project.updated_at,motion}},f);assert.equal(r.status,200);assert.equal(f.written.project_payload.render_settings.volume,.2);assert.equal(f.written.project_payload.subtitles[0].text,'keep');});
test('submitted and stale projects cannot be overwritten',async()=>{for(const changes of [{submitted_at:'submitted'}, {status:'approved'},{}]){const f=fixture(changes);const r=await main({worker_role:'preparation',path:`/api/local/projects/${id}/settings`,method:'POST',body:{version:changes.submitted_at||changes.status?f.project.updated_at:'old-version',motion}},f);assert.equal(r.status,409);assert.equal(f.written,undefined)}});
test('native writes use the original motion validator',async()=>{const f=fixture();await assert.rejects(main({worker_role:'preparation',path:`/api/local/projects/${id}/settings`,method:'POST',body:{version:f.project.updated_at,motion:{...motion,fps:60}}},f));assert.equal(f.written,undefined)});
test('local adapter cannot call submission or publishing routes',async()=>{const f=fixture();const r=await main({worker_role:'preparation',path:`/api/std/projects/${id}/submit`,method:'POST',body:{}},f);assert.equal(r.status,404);assert.equal(f.written,undefined)});

test('unified worker cannot edit pre-submit preparation settings',async()=>{const f=fixture();const r=await main({worker_role:'postproduction',path:`/api/local/projects/${id}/settings`,method:'POST',body:{version:f.project.updated_at,motion}},f);assert.equal(r.status,409);assert.equal(f.written,undefined)});
