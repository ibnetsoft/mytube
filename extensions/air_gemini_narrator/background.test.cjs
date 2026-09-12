const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup() {
  const store = {}, downloads = [];
  let handler;
  const chrome = {
    action: {onClicked: {addListener() {}}},
    runtime: {id: 'self', onMessage: {addListener(fn) {handler = fn;}}},
    storage: {local: {async set(data) {Object.assign(store, data);}, async get(key) {return {[key]: store[key]};}}},
    downloads: {
      async download(opts) {downloads.push(opts); return 7;},
      async search() {return [{id: 7, state: 'complete'}];},
      onChanged: {addListener() {}}
    }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'background.js'), 'utf8'), {chrome});
  const sender = {id: 'self', tab: {url: 'https://gemini.google.com/app'}};
  const payload = {type: 'air-save', id: '12345678-1234-1234-1234-123456789abc', dataUrl: 'data:audio/mpeg;base64,SUQz'};
  return {store, downloads, handler, sender, payload, send: msg => new Promise(resolve => handler(msg, sender, resolve))};
}
test('fast download is marked complete even if its event preceded the job mapping', async () => {
  const s = setup();
  assert.equal((await s.send(s.payload)).ok, true);
  assert.equal(s.store['download-7'].state, 'complete');
  assert.equal(s.downloads[0].filename, `AIR-Narration/${s.payload.id}.mp3`);
});
test('reject unknown media formats rather than relabel bytes as MP3', async () => {
  const s = setup();
  assert.equal((await s.send({...s.payload, dataUrl: 'data:application/octet-stream;base64,AAAA'})).ok, false);
  assert.equal(s.downloads.length, 0);
});
test('reject paths and foreign-page download requests', async () => {
  const s = setup();
  assert.equal((await s.send({...s.payload, id: '../../outside'})).ok, false);
  assert.equal(s.handler(s.payload, {id: 'self', tab: {url: 'https://example.com'}}, () => assert.fail()), undefined);
  assert.equal(s.downloads.length, 0);
});
