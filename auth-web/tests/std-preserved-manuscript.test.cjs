const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const cache = new Map();
function load(file) {
    file = path.resolve(file);
    if (cache.has(file)) return cache.get(file);
    if (file.endsWith('.json')) return JSON.parse(fs.readFileSync(file, 'utf8'));
    const exports = {};
    cache.set(file, exports);
    const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText;
    vm.runInNewContext(source, { exports, console, process, require(name) {
        if (name === 'next/server') return { NextResponse: {} };
        if (name === '@supabase/supabase-js') return { createClient: () => { throw Error('No network in this test'); } };
        if (name === './supabaseAdmin') return { supabaseAdmin: {} };
        if (!name.startsWith('.')) throw Error(`Unexpected dependency: ${name}`);
        const target = path.resolve(path.dirname(file), name);
        return load(path.extname(target) ? target : target + '.ts');
    }});
    return exports;
}
const { buildStdScenes } = load(path.join(__dirname, '../lib/stdWeb.ts'));
test('a long Japanese manuscript keeps every existing scene boundary on claim', () => {
    const scenes = Array.from({ length: 101 }, (_, i) => ({
        scene_number: i + 1,
        scene_text: `第${i + 1}の場面。` + '大五郎はお鈴の話を静かに聞いておりました。'.repeat(6),
        duration_seconds: i < 18 ? 5 : 18,
        image_prompt: `jidaigeki_cel scene ${i + 1}`,
    }));
    const topic = { language: 'ja', assigned_duration_minutes: 22, assigned_image_style: 'jidaigeki_cel',
        pregenerated_script: scenes.map(s => s.scene_text).join('\n\n'),
        pregenerated_structure: { scenes } };
    const result = buildStdScenes(topic);
    assert.equal(result.length, 101);
    result.forEach((s, i) => assert.equal(s.scene_text, scenes[i].scene_text));
    assert.equal(result.map(s => s.scene_text).join('\n\n'), topic.pregenerated_script);
});
test('edited manuscript text takes precedence over stale scene text', () => {
    const result = buildStdScenes({ pregenerated_script: '新しい本文です。娘は父の手を取りました。',
        pregenerated_structure: { scenes: [{ scene_text: '古い本文です。' }] } });
    assert.equal(result[0].scene_text, '新しい本文です。娘は父の手を取りました。');
});
test('actual imported package passes web readiness and preserves its complete Japanese script', () => {
    if (!process.env.MANUSCRIPT_TOPIC_FILE) return;
    const topic = JSON.parse(fs.readFileSync(process.env.MANUSCRIPT_TOPIC_FILE, 'utf8'));
    const { isPreparedUserTopic } = load(path.join(__dirname, '../lib/preparedTopic.ts'));
    assert.equal(isPreparedUserTopic(topic), true);
    const scenes = buildStdScenes(topic);
    assert.equal(scenes.map(s => s.scene_text).join('\n\n'), topic.pregenerated_script);
    assert.equal(scenes.reduce((n,s) => n+s.duration_seconds, 0), 1320);
    assert.equal(topic.language, 'ja');
    assert.ok(!/[가-힣]/u.test(topic.pregenerated_script));
});
