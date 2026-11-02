const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const { spawnSync } = require('node:child_process')
const esbuild = require('esbuild')
const { chromium } = require('@playwright/test')

const root = path.resolve(__dirname, '../..')
const source = esbuild.buildSync({ entryPoints: [path.join(root, 'auth-web/components/StdSubtitleOverlay.tsx')],
    bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react', 'react/jsx-runtime'] }).outputFiles[0].text
const moduleFilename = path.join(root, 'auth-web/tests/subtitle-wrap-module.cjs')
const mod = new Module(moduleFilename, module)
mod.paths = module.paths
mod._compile(source, moduleFilename)
const algorithm = mod.exports.wrapSubtitleLines.toString()
const samples = ['ABCDEFGHIJK', '字幕を読みやすい位置で区切り、一文字だけが残らないように表示します。',
    '父の店を残したいと話せば、清吉はいつも耳を傾けてくれました。その顔を思うと、僕の紹介状が妙に重く感じられます。',
    'A longer English sentence, with natural breaks and punctuation.',
    '昔、横浜の仕立屋の志乃に、こんな縁談があったそうです。',
    '道すがら、志乃は父を亡くしてからの忙しさをぽつりと話します。',
    '清吉と知り合ったのは、客の届け物を手伝ってもらった折のこと。重い包みを下ろし、仕事の済むまで待ってくれた人です。',
    '婚礼を前に、相手の戸籍の書面を開いたところ、聞いていた父母の名が、どちらも見当たりません。',
    'かつての思い出、家族の秘密、そして彼女が見つけた一通の手紙を語ります。',
    'นี่คือเรื่องราวของครอบครัวและความทรงจำที่ไม่เคยลืมเลือนในชีวิต']

;(async () => {
    const browser = await chromium.launch({ headless: true, channel: 'chrome' })
    try {
        const page = await browser.newPage()
        for (const font of ['NotoSansJP-Bold', 'GmarketSansBold']) {
            const catalog = require('../public/fonts/catalog.json')
            const bytes = fs.readFileSync(path.join(root, 'auth-web/public/fonts', catalog[font])).toString('base64')
            const fallback = fs.readFileSync(path.join(root, 'auth-web/public/fonts', catalog['NotoSansJP-Bold'])).toString('base64')
            const thai = fs.readFileSync(path.join(root, 'auth-web/public/fonts', catalog.NotoSansThai)).toString('base64')
            await page.setContent(`<style>@font-face{font-family:TestFace;src:url(data:font/woff;base64,${bytes})}@font-face{font-family:Fallback;src:url(data:font/woff;base64,${fallback})}@font-face{font-family:Thai;src:url(data:font/ttf;base64,${thai})} body{font-family:TestFace}</style><div>sample</div>`)
            await page.evaluate(() => Promise.all([document.fonts.load('16px TestFace'), document.fonts.load('16px Fallback'), document.fonts.load('16px Thai')]))
            const widths = [320, 440, 1000, 1920]
            const browserLines = await page.evaluate(({algorithm, samples, widths}) => {
                const wrap = (0, eval)(`(${algorithm})`)
                const context = document.createElement('canvas').getContext('2d')
                return widths.map(width => {
                    const size = width * 15.12 / 440
                    context.font = `400 ${size}px TestFace, Fallback, Thai, sans-serif`
                    return samples.map(text => wrap(text, str => context.measureText(str).width, width * .85 - size * 1.2))
                })
            }, { algorithm, samples, widths })
            const script = `import json,sys,tempfile\nfrom services.ffmpeg_slideshow_service import _prepare_fonts_dir,_subtitle_measure_with_fallback\nfrom services.subtitle_layout import wrap_subtitle_lines\nfont=sys.argv[1]\nrows,widths=json.loads(sys.stdin.read())\nout=[]\nwith tempfile.TemporaryDirectory() as d:\n fonts=_prepare_fonts_dir(d,{'fontFamily':font})\n for width in widths:\n  size=width*15.12/440\n  measure=_subtitle_measure_with_fallback(fonts,font,size)\n  out.append([wrap_subtitle_lines(s,measure,width*.85-size*1.2) for s in rows])\nprint(json.dumps(out,ensure_ascii=True))`
            const python = spawnSync('python', ['-c', script, font], { cwd: root, input: JSON.stringify([samples, widths]), encoding: 'utf8', env: {...process.env, PYTHONIOENCODING: 'utf-8'} })
            assert.equal(python.status, 0, python.stderr)
            const renderLines = JSON.parse(python.stdout)
            for (let w = 0; w < widths.length; w++) for (let i = 0; i < samples.length; i++) {
                assert.deepEqual(browserLines[w][i], renderLines[w][i], `${font}, width ${widths[w]}: ${samples[i]}`)
                assert.equal(browserLines[w][i].join('').replace(/\s/g, ''), samples[i].replace(/\s/g, ''))
                assert(browserLines[w][i].length === 1 || browserLines[w][i].every(line => Array.from(line).length !== 1))
            }
        }
        console.log('Browser and renderer line wrapping match for fixture fonts and samples.')
    } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
