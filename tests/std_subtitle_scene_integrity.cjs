const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '..');
const ts = require(process.env.TYPESCRIPT_PATH || path.join(root, 'auth-web/node_modules/typescript'));
function load(name) {
  const filename = path.join(root, 'auth-web/lib', name + '.ts');
  const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }, reportDiagnostics: true });
  assert.equal((result.diagnostics || []).length, 0);
  const mod = new Module(filename, module); mod._compile(result.outputText, filename); return mod.exports;
}
const subtitles = load('stdSubtitles');
const integrity = load('stdSubtitleSceneIntegrity');
for (const count of [28, 53, 161]) {
  const scenes = Array.from({length: count}, (_, i) => ({scene_number: i + 1, scene_text: `${i + 1}번째 이야기입니다. ` + '한 가족의 이야기가 천천히 이어졌습니다. '.repeat(12), image_url: `https://example.com/${i + 1}.png`}));
  const script = scenes.map(s => s.scene_text).join('\n\n');
  assert.equal(subtitles.estimateRequiredSceneCount(script, count), count);
  assert.deepEqual(subtitles.partitionScriptByExistingSceneBoundaries(script, scenes, count), scenes.map(s=>s.scene_text.trim()));
  const generated = subtitles.generateSynchronizedSubtitles(script, scenes, 20);
  assert.equal(Math.max(...generated.map(s => s.scene_number)), count);
  assert.equal(integrity.subtitlesMatchSceneManifest(generated, scenes), true);
}
assert.equal(subtitles.estimateRequiredSceneCount('가'.repeat(4879), 0), 55);
const scenes = Array.from({length: 53}, (_, i) => ({scene_number:i+1,image_url:`image-${i+1}`}));
assert.equal(integrity.findExactSubtitleScene({scene_number:53}, scenes).image_url, 'image-53');
for (const number of [0, -1, 54, 55, 1.5, NaN]) assert.equal(integrity.findExactSubtitleScene({scene_number:number},scenes,[...scenes,...scenes]),null);
assert.equal(integrity.findExactSubtitleScene({}, scenes),null);
assert.equal(integrity.findExactSubtitleScene({scene_number:54}, scenes, [{scene_number:54,image_url:'stale'}]),null);
assert.equal(integrity.findExactSubtitleScene({scene_number:54,image_url:'stale-first-image'},scenes),null);
const valid=scenes.map(s=>({scene_number:s.scene_number,text:'대본'}));
assert.equal(integrity.subtitlesMatchSceneManifest(valid,scenes),true);
assert.equal(integrity.subtitlesMatchSceneManifest([...valid,{scene_number:54}],scenes),false);
assert.equal(integrity.subtitlesMatchSceneManifest(valid.slice(0,-1),scenes),false);
assert.equal(integrity.subtitlesMatchSceneManifest([...valid].reverse(),scenes),false);
const page=fs.readFileSync(path.join(root,'auth-web/app/std/page.tsx'),'utf8');
const visualSection=page.slice(page.indexOf('const subtitleSceneVisual'),page.indexOf('const subtitleHasValidTiming'));
assert(!visualSection.includes('scenes[0]') && !visualSection.includes('payloadScenes[sceneNumber - 1]'));
assert(!visualSection.includes('runtimeAssetUrl(subtitle?.image_url'));
assert(page.includes('subtitlesMatchSceneManifest(savedSubtitles, scenes)'));
console.log('PASS: explicit 28/53/161 scenes; long scripts; exact boundaries; invalid cached mappings; missing image never substituted.');
