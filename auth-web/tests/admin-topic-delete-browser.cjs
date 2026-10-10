const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const ts = require('typescript')
const { chromium } = require('@playwright/test')

// Render the real dialog in a local React harness. API responses are fixtures;
// no test request can reach the production application or delete live topics.
const web = path.resolve(__dirname, '..')
const output = path.resolve(web, '../output/admin-topic-delete-qa-20261011')
const componentFile = path.join(web, 'components/AdminTopicDeleteDialog.tsx')
const fixtures = [
    { id: 4101, topic: '중국 시골집 벽장에 숨었던 9개월, 문밖에서 들린 한국말', category_id: 1, category_name: '탈북사연', video_type: 'longform', status: 'excluded' },
    { id: 4102, topic: '서울 역에서 다시 만난 가족', category_id: 1, category_name: '탈북사연', video_type: 'longform', status: 'pending' },
    { id: 4201, topic: '폭설 속 우체통에 놓인 낡은 장갑', category_id: 2, category_name: '해외감동', video_type: 'longform', status: 'excluded' },
    { id: 4301, topic: '68세 경비원에게 배달된 빨간 구두 한 켤레', category_id: 3, category_name: '황혼19금', video_type: 'shorts', status: 'pending' },
    { id: 4302, topic: '제작 중인 프로젝트의 주제', category_id: 3, category_name: '황혼19금', video_type: 'longform', status: 'pending', delete_block_reason: '진행 중인 프로젝트가 연결되어 있습니다.' },
].map(topic => ({ ...topic, id: String(topic.id), category_id: String(topic.category_id) }))

function browserModules(entry) {
    const modules = new Map()
    function add(file) {
        const key = path.relative(web, file).replaceAll(path.sep, '/')
        if (modules.has(key)) return key
        const source = fs.readFileSync(file, 'utf8')
        const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.React, esModuleInterop: true, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
        modules.set(key, '')
        const dependencies = {}
        for (const [, specifier] of compiled.matchAll(/require\("([^"]+)"\)/g)) {
            if (!specifier.startsWith('.') && !specifier.startsWith('@/')) continue
            const base = specifier.startsWith('@/') ? path.join(web, specifier.slice(2)) : path.resolve(path.dirname(file), specifier)
            const resolved = ['', '.ts', '.tsx', '.js', '/index.ts', '/index.tsx'].map(ext => base + ext).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile())
            assert(resolved, `Resolve browser dependency ${specifier}`)
            dependencies[specifier] = add(resolved)
        }
        modules.set(key, `modules[${JSON.stringify(key)}] = function(module,exports,require){\nconst React=window.React;\n${compiled}\n}; maps[${JSON.stringify(key)}]=${JSON.stringify(dependencies)};`)
        return key
    }
    const entryKey = add(entry)
    return `(function(){const modules={},maps={},cache={};${[...modules.values()].join('\n')}\nfunction load(id){if(cache[id])return cache[id].exports;const module={exports:{}};cache[id]=module;modules[id](module,module.exports,name=>name==='react'?window.React:name==='lucide-react'?window.LucideReact:load(maps[id][name]));return module.exports;}window.Dialog=load(${JSON.stringify(entryKey)}).default;})();`
}

async function main() {
    fs.mkdirSync(output, { recursive: true })
    const css = await require('postcss')([require('@tailwindcss/postcss')({ base: web })]).process('@import "tailwindcss";\n@source "../components/AdminTopicDeleteDialog.tsx";', { from: path.join(web, 'app/admin-topic-delete-qa.css') })
    const assets = {
        '/react.js': fs.readFileSync(path.join(web, 'node_modules/react/umd/react.development.js')),
        '/react-dom.js': fs.readFileSync(path.join(web, 'node_modules/react-dom/umd/react-dom.development.js')),
        '/lucide.js': fs.readFileSync(path.join(web, 'node_modules/lucide-react/dist/umd/lucide-react.js')),
        '/dialog.js': browserModules(componentFile),
        '/styles.css': css.css,
    }
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><style>body{margin:0;background:#080b15;color:white;font-family:Arial,sans-serif}</style></head><body><div id="root"></div><script src="/react.js"></script><script src="/react-dom.js"></script><script>window.react=React</script><script src="/lucide.js"></script><script src="/dialog.js"></script><script>window.events={closed:0,deleted:[]};ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Dialog,{adminFetch:(url,options)=>fetch(url,options),initialLanguage:'ko',onClose:()=>window.events.closed++,onDeleted:(result)=>window.events.deleted.push(result)}));</script></body></html>`
    const server = http.createServer((req, res) => {
        const name = new URL(req.url, 'http://localhost').pathname
        if (name === '/') { res.setHeader('content-type', 'text/html'); res.end(html); return }
        if (name in assets) { res.setHeader('content-type', name.endsWith('.js') ? 'text/javascript' : 'text/css'); res.end(assets[name]); return }
        res.writeHead(404); res.end('Fixture route not found')
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const origin = `http://127.0.0.1:${server.address().port}`
    const executablePath = process.env.ADMIN_TOPIC_QA_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    const browser = await chromium.launch({ headless: true, executablePath: fs.existsSync(executablePath) ? executablePath : undefined })
    const results = []
    const pageErrors = []
    const externalRequests = []
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
        const requests = []
        let deleteResult = { success: true, deletedIds: ['4101'], skipped: [{ id: '4201', reason: '연결된 프로젝트가 있어 삭제할 수 없습니다.' }] }
        let deleteFailure = false
        let deleteWait = null
        let largeList = false
        page.on('pageerror', error => pageErrors.push(error.message))
        await page.route('**/*', async route => {
            const url = new URL(route.request().url())
            if (url.origin !== origin) { externalRequests.push(url.origin); return route.abort() }
            if (url.pathname === '/api/admin/topics-queue/bulk-delete') {
                const method = route.request().method()
                requests.push({ method, query: Object.fromEntries(url.searchParams), body: method === 'DELETE' ? route.request().postDataJSON() : null })
                if (method === 'DELETE') {
                    if (deleteWait) await deleteWait
                    return route.fulfill({ status: deleteFailure ? 500 : 200, json: deleteFailure ? { success: false, error: 'Fixture deletion failed' } : deleteResult })
                }
                const pageNumber = Number(url.searchParams.get('page') || 1)
                const dataset = largeList ? Array.from({ length: 501 }, (_, i) => ({ ...fixtures[1], id: String(6000 + i), topic: i === 500 ? '다른 주제' : `대량 선택 ${i}` })) : fixtures
                const split = largeList ? 500 : 3
                const topics = pageNumber === 1 ? dataset.slice(0, split) : dataset.slice(split)
                return route.fulfill({ json: { success: true, topics, page: pageNumber, perPage: 500, total: dataset.length, hasMore: pageNumber === 1 } })
            }
            return route.continue()
        })
        await page.goto(origin)
        const checkbox = id => page.getByRole('checkbox', { name: `토픽 ${id} 선택`, exact: true })
        const deletes = () => requests.filter(request => request.method === 'DELETE')
        const passed = name => results.push({ name, pass: true })
        await checkbox('4101').waitFor()
        await checkbox('4302').waitFor()
        assert.equal(await checkbox('4302').isDisabled(), true, 'Linked-project topic is protected')
        assert.deepEqual(requests.map(request => request.query), [
            { language: 'ko', page: '1', perPage: '500' }, { language: 'ko', page: '2', perPage: '500' },
        ], 'All category pages loaded before selection')
        assert.equal(await page.getByRole('checkbox').count(), 5)
        passed('Korean topics from every API page and category, including hidden topics; linked projects protected')
        await page.screenshot({ path: path.join(output, 'desktop-initial.png') })

        await page.getByLabel('카테고리', { exact: true }).selectOption('1')
        await page.getByRole('button', { name: '검색 결과 전체 선택', exact: true }).click()
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 2)
        await page.getByRole('button', { name: '선택 해제', exact: true }).click()
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 0)
        await page.getByLabel('카테고리', { exact: true }).selectOption('all')
        await checkbox('4101').check()
        await page.getByLabel('영상 유형', { exact: true }).selectOption('shorts')
        assert.equal(await page.getByRole('checkbox').count(), 1)
        assert.equal(await checkbox('4301').isChecked(), false)
        await page.getByLabel('영상 유형', { exact: true }).selectOption('all')
        await page.getByLabel('상태', { exact: true }).selectOption('excluded')
        assert.equal(await page.getByRole('checkbox').count(), 2)
        await page.getByLabel('상태', { exact: true }).selectOption('all')
        await page.getByLabel('토픽 검색', { exact: true }).fill('4201')
        assert.equal(await page.getByRole('checkbox').count(), 1)
        await checkbox('4201').check()
        await page.getByLabel('토픽 검색', { exact: true }).fill('')
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 0, 'Changed filter clears hidden selection')
        passed('Category, format, status and search filters; select-all scope; clear selection on filter changes')

        await checkbox('4101').check()
        await checkbox('4201').check()
        await page.getByRole('button', { name: '선택 2개 삭제', exact: true }).click()
        assert.equal(await page.getByRole('heading', { name: '선택한 2개 토픽을 삭제할까요?', exact: true }).count(), 1)
        assert.equal(await page.locator('li').count(), 2)
        assert.equal(deletes().length, 0, 'Selection and confirmation preview do not delete')
        await page.screenshot({ path: path.join(output, 'desktop-confirmation.png') })
        await page.getByRole('button', { name: '돌아가기', exact: true }).click()
        assert.equal(deletes().length, 0, 'Cancel does not delete')
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 2)
        passed('Cross-category selection receives concrete confirmation; cancellation preserves data and selection')

        await page.getByRole('button', { name: '선택 2개 삭제', exact: true }).click()
        let releaseDelete
        deleteWait = new Promise(resolve => { releaseDelete = resolve })
        await page.getByRole('button', { name: '삭제 확정', exact: true }).click()
        await page.getByRole('button', { name: '삭제 중…', exact: true }).waitFor()
        assert.equal(await page.getByRole('button', { name: '삭제 중…', exact: true }).isDisabled(), true)
        assert.equal(await page.getByRole('button', { name: '닫기', exact: true }).isDisabled(), true)
        await page.keyboard.press('Escape')
        assert.equal(await page.evaluate(() => window.events.closed), 0)
        releaseDelete()
        deleteWait = null
        await page.getByRole('status').filter({ hasText: '1개 토픽을 삭제했습니다.' }).waitFor()
        assert.equal(deletes().length, 1)
        assert.deepEqual(deletes()[0].body, { ids: ['4101', '4201'], language: 'ko' })
        assert.equal(await checkbox('4101').count(), 0)
        assert.equal(await checkbox('4201').isDisabled(), true)
        assert.deepEqual(await page.evaluate(() => window.events.deleted), [['4101']])
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 0)
        await page.screenshot({ path: path.join(output, 'desktop-partial-result.png') })
        passed('One explicit DELETE sends only reviewed Korean IDs; pending operation locked; partial result updates only deleted topics')

        await page.reload()
        await checkbox('4102').check()
        deleteFailure = true
        await page.getByRole('button', { name: '선택 1개 삭제', exact: true }).click()
        await page.getByRole('button', { name: '삭제 확정', exact: true }).click()
        await page.getByRole('alert').filter({ hasText: 'Fixture deletion failed' }).waitFor()
        assert.equal(await page.getByRole('button', { name: '삭제 확정', exact: true }).isEnabled(), true)
        await page.getByRole('button', { name: '돌아가기', exact: true }).click()
        assert.equal(await checkbox('4102').isChecked(), true)
        assert.deepEqual(await page.evaluate(() => window.events.deleted), [])
        passed('API failure surfaces an error and preserves selected topic for retry')

        await page.setViewportSize({ width: 390, height: 844 })
        await page.getByRole('button', { name: '선택 해제', exact: true }).click()
        const geometry = await page.getByRole('dialog').evaluate(element => {
            const box = element.getBoundingClientRect()
            const tableViewport = element.querySelector('table').parentElement.getBoundingClientRect()
            const firstRow = element.querySelector('tbody tr').getBoundingClientRect()
            const visibleRowHeight = Math.max(0, Math.min(firstRow.bottom, tableViewport.bottom) - Math.max(firstRow.top, tableViewport.top))
            return { x: box.x, right: box.right, bottom: box.bottom, visibleRowHeight, documentOverflow: document.documentElement.scrollWidth > innerWidth }
        })
        assert.equal(geometry.documentOverflow, false)
        assert(geometry.x >= 0 && geometry.right <= 390 && geometry.bottom <= 844)
        assert(geometry.visibleRowHeight >= 30, 'A topic row remains visible below filters on a narrow screen')
        await page.screenshot({ path: path.join(output, 'mobile-dialog.png') })
        await page.getByRole('button', { name: '닫기', exact: true }).focus()
        await page.keyboard.press('Shift+Tab')
        assert.equal(await page.getByRole('dialog').evaluate(element => element.contains(document.activeElement)), true)
        await page.keyboard.press('Escape')
        assert.equal(await page.evaluate(() => window.events.closed), 1)
        passed('Narrow viewport remains within screen, keyboard focus stays in dialog and Escape closes safely')

        largeList = true
        await page.setViewportSize({ width: 1440, height: 1000 })
        await page.reload()
        await checkbox('6000').waitFor()
        assert.equal(await page.getByRole('checkbox').count(), 50, 'Long lists use 50-row UI pages')
        assert.equal(await page.getByRole('button', { name: '검색 결과 전체 선택', exact: true }).isDisabled(), true, '501 topics cannot be bulk selected')
        await page.getByRole('button', { name: '다음', exact: true }).click()
        await checkbox('6050').waitFor()
        await page.getByLabel('토픽 검색', { exact: true }).fill('대량 선택')
        await checkbox('6000').waitFor()
        await page.getByRole('button', { name: '검색 결과 전체 선택', exact: true }).click()
        assert.equal(await page.getByRole('button', { name: '선택 500개 삭제', exact: true }).isEnabled(), true)
        assert.equal(await page.getByRole('checkbox', { checked: true }).count(), 50, 'Select all spans matching UI pages')
        assert.equal(deletes().length, 2, 'Large selection never deletes without confirmation')
        passed('Long lists paginate; 500 limit enforced; filtered select-all spans UI pages without issuing DELETE')
        assert.deepEqual(pageErrors, [], 'No uncaught browser errors')
        assert.deepEqual(externalRequests, [], 'No production or third-party requests')
        fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ results, requests, pageErrors, externalRequests }, null, 2))
        console.log(`PASS: ${results.length} admin topic deletion browser checks; ${output}`)
    } finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
