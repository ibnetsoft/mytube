const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict')
const ts = require('typescript'), { chromium } = require('@playwright/test')
async function main() {
    const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
    try {
        const page = await browser.newPage({ viewport: { width: 1100, height: 850 } })
        page.setDefaultTimeout(10000)
        const errors = []; page.on('pageerror', e => errors.push(e.message))
        let reads = 0, uploaded = false, requested = false, disabled = false
        const scene = { number: 1, title: '바람 속 인물', source: null, preparation: null }
        await page.route('http://ae-scene.test/**', async route => {
            const req = route.request(), url = new URL(req.url())
            if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<html><body><div id="root"></div></body></html>' })
            if (url.pathname === '/upload') {
                assert.equal(req.method(), 'PUT'); assert.equal(req.headers()['content-type'], 'image/vnd.adobe.photoshop')
                assert.equal(req.postDataBuffer().toString(), '8BPS-test'); uploaded = true
                return route.fulfill({ status: 200, body: '' })
            }
            if (url.pathname.endsWith('/assets/init')) {
                assert.equal(req.postDataJSON().asset_type, 'original')
                return route.fulfill({ json: { storage_upload_url: 'http://ae-scene.test/upload', storage_bucket: 'b', storage_path: 'scene.psd' } })
            }
            if (url.pathname.endsWith('/assets/complete')) {
                assert.ok(uploaded); scene.source = { id: 'psd', file_name: 'scene.psd' }
                return route.fulfill({ json: { success: true } })
            }
            if (req.method() === 'POST') {
                const body = req.postDataJSON()
                assert.equal(body.scene_number, 1)
                if (body.action === 'prepare') {
                    assert.equal(body.source_asset_id, 'psd'); assert.match(body.direction_text, /머리카락/)
                    assert.deepEqual(body.requested_effects, ['atmospheric_haze', 'focus_glow'])
                    requested = true
                    scene.preparation = { id: 'prep', enabled: true, state: 'queued', direction_text: body.direction_text, requested_effects: body.requested_effects }
                } else {
                    assert.equal(body.action, 'disable'); disabled = true
                    scene.preparation = { ...scene.preparation, enabled: false, state: 'disabled' }
                }
            } else reads++
            return route.fulfill({ json: { editable: true, scenes: [scene] } })
        })
        await page.goto('http://ae-scene.test')
        for (const pkg of ['react', 'react-dom']) await page.addScriptTag({ path: path.join(path.dirname(require.resolve(pkg + '/package.json')), 'umd/' + pkg + '.development.js') })
        const effectModule = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdAeSceneEffects.ts'), 'utf8'), { compilerOptions: { module: 1, target: 9 } }).outputText
        await page.addScriptTag({content: `var effectExports={};(function(exports){${effectModule}})(effectExports);`})
        const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../components/StdAeScenePreparation.tsx'), 'utf8'), { compilerOptions: { module: 1, target: 9, jsx: 4 } }).outputText
        await page.addScriptTag({ content: `var exports={};function require(n){if(n==='../lib/stdAeSceneEffects')return effectExports;if(n==='react')return React;if(n==='react/jsx-runtime')return {jsx:(t,p,k)=>React.createElement(t,{...p,key:k}),jsxs:(t,p,k)=>React.createElement(t,{...p,key:k}),Fragment:React.Fragment};throw Error(n)};${compiled};ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(exports.default,{projectId:'fixture',headers:{Authorization:'Bearer fixture'}}));` })
        const cssDir = path.join(__dirname, '../.next/static/css')
        if (fs.existsSync(cssDir)) for (const name of fs.readdirSync(cssDir).filter(name => name.endsWith('.css')))
            await page.addStyleTag({ path: path.join(cssDir, name) })
        assert.equal(reads, 0)
        await page.getByText('PSD로 AE 장면 연출', { exact: true }).click()
        await page.getByLabel('작업할 씬').waitFor()
        await page.getByLabel('원본 PSD / PSB').setInputFiles({ name: 'scene.psd', mimeType: 'image/vnd.adobe.photoshop', buffer: Buffer.from('8BPS-test') })
        await page.getByText('scene.psd', { exact: true }).waitFor()
        await page.getByLabel('원하는 연출').fill('머리카락 끝을 움직이고 얼굴로 접근')
        await page.getByLabel('안개', { exact: true }).check()
        await page.getByLabel('부분 발광', { exact: true }).check()
        await page.getByRole('button', { name: '레이어·연출 준비', exact: true }).click()
        await page.getByRole('status').filter({ hasText: '준비 대기' }).waitFor()
        assert.equal(requested, true)
        assert.equal(await page.getByRole('button', { name: '레이어·연출 준비', exact: true }).isDisabled(), true)
        await page.screenshot({ path: '/tmp/ae-scene-preparation.png', fullPage: true })
        await page.getByRole('button', { name: '이 씬의 PSD 연출 사용 안 함', exact: true }).click()
        await page.getByRole('status').filter({ hasText: '사용 안 함' }).waitFor()
        assert.equal(disabled, true); assert.deepEqual(errors, [])
        console.log('PASS: lazy panel, original PSD upload, normalized pre-TTS direction request, pending lock, explicit disable')
    } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
