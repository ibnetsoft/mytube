const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../auth-web/node_modules/typescript');
function load(file, requireStub = require) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText;
  new Function('exports', 'require', code)(exports, requireStub);
  return exports;
}
const { isCurrentMediaScope, assetBelongsToProject } = load('auth-web/lib/stdMediaScope.ts');
const a = { session: 'user-a', projectId: 'project-a', generation: 1 };
assert.equal(isCurrentMediaScope(a, { ...a }), true);
for (const changed of [{ session: 'user-b' }, { projectId: 'project-b' }, { generation: 3 }, { session: '' }]) {
  assert.equal(isCurrentMediaScope(a, { ...a, ...changed }), false);
}
assert.equal(assetBelongsToProject({ project_id: 'project-b' }, 'project-a'), false);
assert.equal(assetBelongsToProject({ project_id: 'project-a' }, 'project-a'), true);

const projectId = 'f5a7efe8-e1bd-435c-adb8-8c213bff4db2';
let email = 'user-a@example.com', downloads = [];
const rows = {
  std_projects: [{ id: projectId, employee_email: email }],
  std_project_assets: [
    { id: 'asset-a', project_id: projectId, drive_file_id: 'drive-a', status: 'assigned', metadata: {} },
    { id: 'asset-b', project_id: 'other-project', drive_file_id: 'drive-b', status: 'assigned', metadata: {} },
    { id: 'old', project_id: projectId, drive_file_id: 'old-drive', status: 'replaced', metadata: {} },
  ],
};
class Reply extends Response { static json(value, init) { return new Reply(JSON.stringify(value), init); } }
const route = load('auth-web/app/api/std/projects/[projectId]/assets/file/route.ts', name => {
  if (name === 'next/server') return { NextResponse: Reply };
  if (name === '@/lib/stdWeb') return { requireStdUser: async () => ({ ok: true, requester: { email } }) };
  if (name === '@/lib/stdGoogleDrive') return { downloadStdDriveFile: async id => { downloads.push(id); return Buffer.from('video'); } };
  if (name === '@/lib/supabaseAdmin') return { supabaseAdmin: { from(table) {
    let selected = rows[table];
    const query = {
      select() { return query; },
      eq(k, v) { selected = selected.filter(r => r[k] === v); return query; },
      in(k, values) { selected = selected.filter(r => values.includes(r[k])); return query; },
      limit(n) { selected = selected.slice(0, n); return query; },
      async maybeSingle() { return { data: selected[0] || null, error: null }; },
    };
    return query;
  } } };
  throw new Error(name);
});
(async () => {
  // Execute the actual upload handler while its network request is pending.
  const page = fs.readFileSync(path.join(__dirname, '../auth-web/app/std/page.tsx'), 'utf8');
  const handler = page.slice(page.indexOf('    const uploadAsset = async ('), page.indexOf('    const splitTtsTextForBrowser ='));
  for (const transition of ['none', 'project', 'account', 'away-and-back', 'failed-after-switch']) {
    let state = { project: { id: 'project-a', status: 'in_progress' }, scenes: [{ scene_number: 1 }], assets: [] };
    const scope = { current: { ...a } };
    let complete;
    const waiting = new Promise(resolve => { complete = resolve; });
    let remembered = 0;
    const deps = {
      selectedProject: state, mediaScopeRef: scope, isCurrentMediaScope, assetBelongsToProject,
      setSelectedProject: fn => { state = fn(state); },
      isStdRequiredVideoScene: () => true, setMessage() {}, setUploadingKey() {},
      inferVisualMimeType: () => 'video/mp4', DRIVE_DIRECT_UPLOAD_THRESHOLD_BYTES: Infinity,
      authedUploadHeaders: {}, fetch: () => waiting, safeParseJson: async res => res,
      projectAssetCacheKey: () => 'cache-a', projectMediaObjectUrlsRef: { current: {} },
      assetDisplayUrl: () => '/project-a/asset', rememberProjectState: () => { remembered++; },
      setProjects() {}, URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
      FormData: class { set() {} },
    };
    const code = ts.transpileModule(handler + '\nreturn uploadAsset;', {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText;
    const upload = new Function(...Object.keys(deps), code)(...Object.values(deps));
    const result = upload({ scene_number: 1 }, 'video', { name: 'clip.mp4', type: 'video/mp4', size: 12 });
    if (transition !== 'none') {
      scope.current = { ...a, generation: 2, ...(transition === 'account' ? { session: 'user-b' } : {}) };
      state = { project: { id: transition === 'away-and-back' ? 'project-a' : 'project-b' }, scenes: [{ scene_number: 1 }], assets: [] };
    }
    complete({ ok: transition !== 'failed-after-switch', success: transition !== 'failed-after-switch', asset: { id: 'uploaded-a', project_id: 'project-a', scene_number: 1, asset_type: 'video' } });
    assert.equal(await result, transition === 'none' ? 'synced' : false, transition);
    assert.equal(remembered, transition === 'none' ? 1 : 0, transition);
    assert.equal(Boolean(state.scenes[0].video_url), transition === 'none', transition);
    assert.equal(state.assets.length, transition === 'none' ? 1 : 0, transition);
  }
  for (const query of ['assetId=asset-b', 'driveFileId=drive-b', 'assetId=missing&driveFileId=drive-b', 'driveFileId=old-drive']) {
    const reply = await route.GET(new Request('https://test/assets?' + query), { params: { projectId } });
    assert.equal(reply.status, 404, query);
  }
  assert.deepEqual(downloads, []);
  for (const query of ['assetId=asset-a', 'driveFileId=drive-a']) {
    const reply = await route.GET(new Request('https://test/assets?' + query), { params: { projectId } });
    assert.equal(reply.status, 200);
    assert.match(reply.headers.get('cache-control'), /no-store/);
  }
  email = 'admin-looking-but-not-owner@example.com';
  assert.equal((await route.GET(new Request('https://test/assets?assetId=asset-a'), { params: { projectId } })).status, 404);
  assert.deepEqual(downloads, ['drive-a', 'drive-a']);
  console.log('PASS: media scope transitions, asset ownership, foreign/missing/replaced IDs, owner access, cache isolation');
})().catch(error => { console.error(error); process.exitCode = 1; });
