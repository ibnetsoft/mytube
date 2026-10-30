const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const { listedProjectStepStatus } = require('./load-ts.cjs')(path.join(__dirname, '../lib/stdProjectListDisplay.ts'))

const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
const start = page.indexOf('    const getListedProjectStepStatus =')
const end = page.indexOf('    const checkedVisibleIds =', start)
assert(start >= 0 && end > start)
const code = ts.transpileModule(page.slice(start, end) + '\nreturn { completeProjects, incompleteProjects, visibleProjects, getListedProjectStepStatus }', { compilerOptions: { target: 9 } }).outputText
function classify(projects, projectsTab, selectedProject = null, projectsRefreshing = false, projectsLoadError = '') {
    return new Function('projects', 'projectsTab', 'selectedProject', 'listedProjectStepStatus', 'projectsRefreshing', 'projectsLoadError', code)(projects, projectsTab, selectedProject, listedProjectStepStatus, projectsRefreshing, projectsLoadError)
}
const project = (id, submitted_at, allDone) => ({ id, submitted_at, step_status: { allDone } })

test('submitted projects with missing steps stay unfinished; fully ready work is complete without submission', () => {
    const missingSubtitles = project('3376', '2026-10-21', false)
    const missingThumbnail = project('3197', '2026-09-21', false)
    const complete = project('3373', '2026-10-04', true)
    const ready = project('ready', null, true)
    const rows = [missingSubtitles, missingThumbnail, complete, ready]
    const result = classify(rows, 'complete')
    assert.deepEqual(result.completeProjects, [complete, ready])
    assert.deepEqual(result.incompleteProjects, [missingSubtitles, missingThumbnail])
    assert.deepEqual(result.visibleProjects, result.completeProjects)
    assert.deepEqual(classify(rows, 'incomplete').visibleProjects, result.incompleteProjects)
})

test('opening an editor or changing its draft does not override saved list completion', () => {
    const row = project('active', null, true)
    const result = classify([row], 'incomplete', { project: project('active', null, false) })
    assert.equal(result.getListedProjectStepStatus(row).allDone, true)
    assert.deepEqual(result.visibleProjects, [])
    assert.equal(result.completeProjects.length, 1)
})

test('refresh and failure states keep the previous rows visible', () => {
    const row = project('old', null, true)
    assert.deepEqual(classify([row], 'complete', null, true).visibleProjects, [row])
    assert.deepEqual(classify([row], 'complete', null, false, 'unavailable').visibleProjects, [row])
})
