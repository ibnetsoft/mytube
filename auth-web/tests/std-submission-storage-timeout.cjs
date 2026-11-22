const test = require('node:test')
const assert = require('node:assert/strict')
const http = require('node:http')
const fs = require('node:fs')
const ts = require('typescript')
const code = ts.transpileModule(fs.readFileSync('lib/stdSubmissionStorage.ts', 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
const mod = {}; new Function('exports', code)(mod)
for (const mode of ['headers', 'body', 'put']) test(`abort a stalled ${mode} without retry`, async () => {
  let calls = 0
  const server = http.createServer((req,res) => { calls++; req.resume(); if (mode === 'body') { res.writeHead(200, {'content-type':'text/plain'}); res.write('partial') } })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    const start = Date.now()
    await assert.rejects(mod.submissionStorageRequest(`http://127.0.0.1:${server.address().port}/`, mode === 'put' ? {method:'PUT',body:'test'} : {}, new AbortController().signal, 250), /시간이 초과/)
    assert.ok(Date.now() - start < 2000)
    assert.equal(calls, 1)
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
})
