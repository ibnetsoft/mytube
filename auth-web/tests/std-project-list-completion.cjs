const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
const start = page.indexOf('    const getListedProjectStepStatus =')
const end = page.indexOf('    const activeTopicTitleKeys =', start)
assert(start >= 0 && end > start)
const code = ts.transpileModule(page.slice(start, end) + '\nreturn { completeProjects, incompleteProjects, visibleProjects, getListedProjectStepStatus }', { compilerOptions: { target: 9 } }).outputText
function classify(projects, projectsTab, selectedProject = null) {
    const getProjectStepStatus = p => p.project?.step_status || p.step_status
    return new Function('projects', 'projectsTab', 'selectedProject', 'getProjectStepStatus', 'audioResultUrl', 'customScriptText', 'localSubtitles', 'thumbBgUrl', code)(projects, projectsTab, selectedProject, getProjectStepStatus, '', '', [], '')
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

test('active project classification uses the same status as its row indicators', () => {
    const row = project('active', null, true)
    const result = classify([row], 'incomplete', { project: project('active', null, false) })
    assert.equal(result.getListedProjectStepStatus(row).allDone, false)
    assert.deepEqual(result.visibleProjects, [row])
    assert.equal(result.completeProjects.length, 0)
})
