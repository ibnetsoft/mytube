const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const ts = require('typescript')
const { chromium } = require('@playwright/test')

async function main() {
    const server = http.createServer((req, res) => {
        if (req.url === '/fonts/Pretendard-Bold.woff') {
            res.setHeader('Content-Type', 'font/woff'); return res.end(fs.readFileSync(path.join(__dirname, '../public/fonts/Pretendard-Bold.woff')))
        }
        res.setHeader('Content-Type', 'text/html')
        res.end(`<style>@font-face{font-family:Pretendard-Bold;src:url('/fonts/Pretendard-Bold.woff');font-weight:700}</style><canvas id="preview"></canvas>`)
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const browser = await chromium.launch({ channel: 'chrome', headless: true })
    try {
        const page = await browser.newPage()
        await page.goto(`http://127.0.0.1:${server.address().port}`)
        const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdTemplateOverlay.ts'), 'utf8'), {
            compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
        }).outputText
        await page.addScriptTag({ content: `window.exports={};${code}` })
        const settings = { std_image_template_enabled: true, std_image_template_bg_url: '/unwanted-image.png',
            std_template_shape_layers: [{ y: 0, height: 100, color: '#ff0000', opacity: 1 }],
            std_template_text_layers: [{ text: 'Transparent text', x: 50, y: 20, fontSize: 14, color: '#fff', fontFamily: 'Pretendard' }] }
        const result = await page.evaluate(async settings => {
            const saved = await exports.templateOverlaySettings(settings)
            const preview = document.querySelector('canvas')
            await exports.drawTemplateOverlay(preview, settings.std_template_text_layers)
            const alpha = preview.getContext('2d').getImageData(0, 0, 1920, 1080).data
            let ink = 0, background = 0, dark = 0
            for (let i = 3; i < alpha.length; i += 4) {
                if (alpha[i]) { ink++; if (Math.min(alpha[i-3], alpha[i-2], alpha[i-1]) < 240) dark++ } else background++
            }
            return { saved, preview: preview.toDataURL('image/png'), ink, background, dark }
        }, settings)
        assert.equal(result.saved.std_image_template_bg_url, null)
        assert.deepEqual(result.saved.std_template_shape_layers, [])
        assert.equal(result.saved.std_template_overlay_png_data_url, result.preview)
        assert.ok(result.ink > 100 && result.background > 1920 * 1080 * .98)
        assert.equal(result.dark, 0, 'Zero stroke must not add a black outline')
        const serverExports = {}
        new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdTemplateOverlayPng.ts'), 'utf8'), {
            compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
        }).outputText)(serverExports, require)
        const packaged = await serverExports.templateOverlayPng(result.saved)
        assert.equal(packaged.toString('base64'), result.preview.split(',')[1])
        await assert.rejects(() => serverExports.templateOverlayPng({ ...result.saved, std_template_overlay_layers: [] }), /저장/)
        const sharp = require('sharp')
        const opaque = await sharp({ create: { width: 20, height: 20, channels: 4, background: '#ff0000' } }).png().toBuffer()
        await assert.rejects(() => serverExports.templateOverlayPng({ ...result.saved,
            std_template_overlay_png_data_url: `data:image/png;base64,${opaque.toString('base64')}` }), /투명/)
        if (process.argv[2]) {
            const project = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
            const original = project.project_payload.render_settings
            const saved = await page.evaluate(settings => exports.templateOverlaySettings(settings), original)
            fs.writeFileSync(path.resolve(__dirname, '../../_dev/artifacts/template_fixed_settings.json'), JSON.stringify(saved, null, 2))
            fs.writeFileSync(path.resolve(__dirname, '../../_dev/artifacts/template_fixed_overlay.png'), Buffer.from(saved.std_template_overlay_png_data_url.split(',')[1], 'base64'))
        }
        console.log('PASS: transparent text only; preview PNG equals saved render input')
    } finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
