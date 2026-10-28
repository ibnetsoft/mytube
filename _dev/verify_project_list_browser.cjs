const fs = require('fs'), path = require('path'), assert = require('assert/strict'), { createRequire } = require('module')
const runtime = require('../scripts/std_web_runtime.cjs'), req = createRequire(path.join(runtime.web, 'package.json'))
const React = req('react'), { renderToStaticMarkup } = req('react-dom/server'), ts = req('typescript'), { chromium } = req('@playwright/test')
const release = fs.readFileSync('_dev/artifacts/project_completion_release_root.txt', 'utf8').trim()
const pageSource = fs.readFileSync(path.join(release, 'auth-web/app/std/page.tsx'), 'utf8')
const projects = JSON.parse(fs.readFileSync('_dev/artifacts/project_list_api_after.json', 'utf8'))
const a = pageSource.indexOf('            {topicProjectOpen && (') + '            {topicProjectOpen && ('.length
const b = pageSource.indexOf('            {isImpersonating && (', a)
assert(a > 0 && b > a)
const jsx = pageSource.slice(a, b).replace(/\s*\)\}\s*$/, '')
const compiled = ts.transpileModule('return (' + jsx + ')', { compilerOptions: { jsx: 2, target: 9 } }).outputText
const icon = props => React.createElement('span', { ...props, 'data-icon': true })
const display = runtime.load('stdProjectListDisplay')
const titles = runtime.loadFile(path.join(release, 'auth-web/lib/stdTopicTitle.ts'))
const noop = () => {}, complete = projects.filter(p => p.step_status.allDone), incomplete = projects.filter(p => !p.step_status.allDone)
const dateStart = pageSource.indexOf('    const formatProjectListDate =')
const dateEnd = pageSource.indexOf('    // 2.', dateStart)
const formatProjectListDate = new Function(ts.transpileModule(pageSource.slice(dateStart, dateEnd) + ';return formatProjectListDate', { compilerOptions: { target: 9 } }).outputText)()
function markup(tab) {
    const context = { React, setTopicProjectOpen: noop, projectsTab: tab, setProjectsTab: noop, incompleteProjects: incomplete, completeProjects: complete,
        projectsLoadError: '', projectsRefreshing: false, loading: false, setProjectsRefreshKey: noop, visibleProjects: tab === 'complete' ? complete : incomplete,
        selectedProject: null, currentLocale: 'ko', localizedProjectTitle: titles.localizedProjectTitle, projectListThumbnailUrl: display.projectListThumbnailUrl,
        isImpersonating: false, impersonateEmail: '', renderSubmissionNotice: null, openProject: noop, ui: x => x, t: () => '영상',
        ImageIcon: icon, RefreshCw: icon, Check: icon, formatProjectListDate, getListedProjectStepStatus: display.listedProjectStepStatus,
        submittingProjectId: '', reopenProjectForRerender: noop, submitProject: noop }
    return renderToStaticMarkup(new Function(...Object.keys(context), compiled)(...Object.values(context)))
}
async function run() {
    const browser = await chromium.launch({ headless: true, channel: 'chrome' })
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, timezoneId: 'Asia/Seoul' })
        await page.route('**/*', route => route.abort())
        const cssDir = path.join(release, 'auth-web/.next/static/css')
        const css = fs.readdirSync(cssDir).filter(file => file.endsWith('.css')).map(file => fs.readFileSync(path.join(cssDir, file), 'utf8')).join('\n')
        for (const tab of ['incomplete', 'complete']) {
            await page.setContent('<!doctype html><meta charset="utf-8"><style>' + css + '</style>' + markup(tab))
            const rows = tab === 'complete' ? complete : incomplete
            assert.equal(await page.locator('tbody tr').count(), rows.length)
            assert.equal(await page.locator('thead th').count(), 16)
            for (let i = 0; i < rows.length; i++) {
                const row = page.locator('tbody tr').nth(i), saved = rows[i], cells = row.locator('td')
                assert.equal(await cells.count(), 16)
                assert.equal((await cells.nth(2).innerText()).trim(), saved.category_name)
                assert.equal((await cells.nth(3).innerText()).trim(), String(saved.topic_queue_id ?? '—'))
                assert.equal((await cells.nth(4).innerText()).trim(), formatProjectListDate(saved.created_at))
                assert.equal((await cells.nth(5).innerText()).trim(), formatProjectListDate(saved.updated_at))
                assert((await cells.nth(6).innerText()).includes(saved.title))
                const flags = ['isTopicDone', 'isPlanningDone', 'isScriptDone', 'isImageDone', 'isTtsDone', 'isSubtitlesDone', 'isThumbnailDone']
                for (let n = 0; n < flags.length; n++) assert.equal((await cells.nth(n + 7).innerText()).trim(), saved.step_status[flags[n]] ? '●' : '○')
                assert.equal((await cells.nth(15).innerText()).trim(), saved.latest_render_version ? `v${saved.latest_render_version}` : '')
                assert.equal(await cells.nth(14).locator('button').isDisabled(), !(saved.submitted_at || saved.step_status.allDone || saved.shared_submission))
            }
            await page.screenshot({ path: path.resolve(`_dev/artifacts/project_list_${tab}_verified.png`), fullPage: true })
        }
        console.log(JSON.stringify({ browser: 'Chrome', verified_rows: projects.length, verified_columns: 16, complete: complete.length, incomplete: incomplete.length }))
    } finally { await browser.close() }
}
run().catch(error => { console.error(error.stack); process.exitCode = 1 })
