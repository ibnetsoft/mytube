const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '..');
const ts = require(process.env.TYPESCRIPT_PATH || path.join(root, 'auth-web/node_modules/typescript'));
const resolveFilename = Module._resolveFilename;
console.error('HOOK TEST');
Module._resolveFilename = function (request, parent, isMain, options) {
  if (request === './stdDialogueAnnotations') return path.resolve(root, 'auth-web/lib/stdDialogueAnnotations.ts');
  try { return resolveFilename.call(this, request, parent, isMain, options); }
  catch (error) {
    if (typeof request === 'string' && request.startsWith('.') && typeof parent?.filename === 'string') {
      const tsPath = path.resolve(path.dirname(parent.filename), `${request}.ts`);
      if (fs.existsSync(tsPath)) return tsPath;
    }
    throw error;
  }
};
require.extensions['.ts'] = (mod, filename) => {
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  mod._compile(output, filename);
};
const filename = path.join(root, 'auth-web/lib/stdSubtitles.ts');
const transpiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  reportDiagnostics: true,
});
assert.equal((transpiled.diagnostics || []).length, 0);
const absolute = path.resolve(root, 'auth-web/lib/stdDialogueAnnotations.ts');
const dependency = new Module(absolute, module);
dependency.filename = absolute; dependency.paths = Module._nodeModulePaths(path.dirname(absolute));
require.extensions['.ts'](dependency, absolute); require.cache[absolute] = dependency;
const loaded = new Module(filename, module);
loaded._compile(transpiled.outputText, filename);
const subtitles = loaded.exports;

assert.equal(subtitles.DEFAULT_15_MINUTE_SCENE_COUNT, 77);
assert.deepEqual(Array.from({ length: 77 }, (_, i) => subtitles.getStandardSceneDuration(i + 1)), [
  ...Array(18).fill(5), ...Array(6).fill(7), ...Array(6).fill(10),
  ...Array(15).fill(12), ...Array(15).fill(15), ...Array(17).fill(18),
]);
const timings = subtitles.calculateLongformSceneTimings([]);
assert.equal(timings.length, 77);
assert.equal(timings.at(-1).end_time, 900);
assert.deepEqual(timings.slice(0, 12).map(item => item.is_video_required), Array(12).fill(true));
assert.equal(timings[12].is_video_required, false);
assert.equal(timings[12].start_time, 60);
assert.equal(timings[17].end_time, 90);
assert.equal(timings[18].duration, 7);
assert.equal(timings[24].duration, 10);
assert.equal(timings[30].duration, 12);
assert.equal(timings[45].duration, 15);
assert.equal(timings[60].duration, 18);
console.log('PASS: 15-minute 77-scene pacing, one-minute video hook, and subtitle timeline boundaries.');
