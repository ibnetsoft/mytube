const fs = require('fs'), path = require('path')
const release = fs.readFileSync('_dev/artifacts/project_completion_release_root.txt', 'utf8').trim()
const web = path.join(release, 'auth-web')
const localPage = 'auth-web/app/std/page.tsx'
let local = fs.readFileSync(localPage, 'utf8')
function change(source, from, to, expected = 1) {
    if (source.split(from).length - 1 !== expected) throw Error('Unexpected replacement: ' + from.slice(0, 100))
    return source.split(from).join(to)
}
function sharedPageFixes(source) {
    source = change(source, 'onClick={() => setTopicProjectOpen(true)}', 'onClick={openProjectList}')
    source = change(source, 'setTopicProjectOpen(true); setMobileMenuOpen(false)', 'openProjectList(); setMobileMenuOpen(false)', 2)
    source = change(source, 'else setTopicProjectOpen(true)', 'else openProjectList()')
    const begin = source.indexOf('                if (openedProject?.project?.id) {')
    const end = source.indexOf('                    await openProject(loadedProjects[0].id', begin)
    if (begin < 0 || end < 0) throw Error('Missing opened project merge')
    source = source.slice(0, begin) + '                if (!openedProject?.project?.id && !urlProjectId && loadedProjects.length > 0 && loadedProjects[0].id !== preferredProjectId) {\n' + source.slice(end)
    // Match both LF and CRLF without rewriting unrelated source.
    const ghost = /                        setProjects\(prev => \{\r?\n                            const exists = prev.some\(p => p.id === cleanedProject.project.id\)\r?\n                            return exists \? prev : \[cleanedProject.project, ...prev\]\r?\n                        \}\)\r?\n/
    if (!ghost.test(source)) throw Error('Missing cached list insertion')
    source = source.replace(ghost, '')
    source = change(source, 'setProjects([loaded.project])', 'setProjects([])')
    source = change(source, 'setProjects([built.project])', 'setProjects([])')
    const optimistic = '        setProjects(prev => prev.map(project => project.id === currentProjectId ? { ...project, title: nextTitle } : project))'
    source = change(source, optimistic, '        // The project list reloads saved titles when opened; drafts stay in the editor.')
    source = change(source, 'title="완료 상태를 유지한 채 새 렌더 버전을 원격 렌더 큐에 등록합니다."', 'title="현재 저장된 프로젝트의 새 렌더 버전을 요청합니다. 필수 조건을 다시 확인합니다."')
    source = source.replaceAll('colSpan={15}', 'colSpan={16}')
    const imgA = source.indexOf('                                                        {projectThumbnailUrl ? (')
    const imgB = source.indexOf('                                                    </td>', imgA)
    if (imgA < 0 || imgB < 0) throw Error('Missing thumbnail')
    source = source.slice(0, imgA) + `                                                        <div className="relative w-9 h-7 rounded border border-white/10 bg-[#14181f] text-gray-600 flex items-center justify-center mx-auto overflow-hidden">
                                                            <ImageIcon className="w-3.5 h-3.5" />
                                                            {projectThumbnailUrl && <img key={projectThumbnailUrl} src={projectThumbnailUrl} alt="" className="absolute inset-0 h-full w-full object-cover"
                                                                onError={event => { event.currentTarget.style.display = 'none' }} />}
                                                        </div>
` + source.slice(imgB)
    return source
}
if (local.includes('onClick={() => setTopicProjectOpen(true)}')) local = sharedPageFixes(local)
fs.writeFileSync(localPage, local)
let source = fs.readFileSync(path.join(web, 'app/std/page.tsx'), 'utf8')
source = change(source, "import { savedStdOutputStepStatus } from '@/lib/stdOutputStepStatus'", "import { savedStdOutputStepStatus } from '@/lib/stdOutputStepStatus'\nimport { listedProjectStepStatus, projectListThumbnailUrl } from '@/lib/stdProjectListDisplay'")
source = change(source, "    const [projectsLoadError, setProjectsLoadError] = useState('')", "    const [projectsLoadError, setProjectsLoadError] = useState('')\n    const [projectsRefreshing, setProjectsRefreshing] = useState(false)\n    const [projectsRefreshKey, setProjectsRefreshKey] = useState(0)")
const effectStart = local.lastIndexOf('    useEffect(() => {', local.indexOf('        if (!topicProjectOpen || !token) return'))
const effectEnd = local.indexOf('    const authedUploadHeaders =', effectStart)
if (effectStart < 0 || effectEnd < 0) throw Error('Missing refresh effect')
source = change(source, '    const authedUploadHeaders =', local.slice(effectStart, effectEnd) + '    const authedUploadHeaders =')
const status = /    const getListedProjectStepStatus = \(project: any\) => selectedProject\?\.project\?\.id === project.id && !project.submitted_at\r?\n        \? getProjectStepStatus\(selectedProject, selectedProject\?\.scenes \|\| \[\], audioResultUrl, customScriptText, localSubtitles, thumbBgUrl\)\r?\n        : getProjectStepStatus\(project\)/
if (!status.test(source)) throw Error('Missing list status')
source = source.replace(status, '    const getListedProjectStepStatus = listedProjectStepStatus')
source = change(source, "    const visibleProjects = projectsTab === 'complete' ? completeProjects : incompleteProjects", "    const visibleProjects = projectsRefreshing || projectsLoadError ? [] : projectsTab === 'complete' ? completeProjects : incompleteProjects")
source = change(source, "projectsLoadError && !projects.length ? '—' : incompleteProjects.length", "projectsRefreshing ? '…' : projectsLoadError ? '—' : incompleteProjects.length")
source = change(source, "projectsLoadError && !projects.length ? '—' : completeProjects.length", "projectsRefreshing ? '…' : projectsLoadError ? '—' : completeProjects.length")
const thumbA = source.indexOf('                                            const projectThumbnailUrl = sanitizeAssetUrl(')
const thumbB = source.indexOf('                                            const isRenderSuccessHighlighted', thumbA)
if (thumbA < 0 || thumbB < 0) throw Error('Missing metadata')
source = source.slice(0, thumbA) + "                                            const projectThumbnailUrl = projectListThumbnailUrl(p.thumbnail_url, isImpersonating ? impersonateEmail : null)\n                                            const latestSubmittedVersion = Number(p.latest_render_version) || 0\n" + source.slice(thumbB)
source = change(source, '{formatProjectListDate(submittedAt)}', '{formatProjectListDate(p.updated_at)}')
source = change(source, "onClick={() => void loadStdData(token, { forceRefresh: true })}", 'onClick={() => setProjectsRefreshKey(value => value + 1)}')
source = change(source, "                                        {!projectsLoadError && visibleProjects.length === 0 && (", '                                        {projectsRefreshing && <tr><td colSpan={16} className="px-4 py-10 text-center text-gray-400" role="status">최신 저장 상태를 불러오는 중…</td></tr>}\n                                        {!projectsRefreshing && !projectsLoadError && visibleProjects.length === 0 && (')
source = sharedPageFixes(source)
fs.writeFileSync(path.join(web, 'app/std/page.tsx'), source)

const route = path.join(web, 'app/api/std/projects/route.ts')
source = fs.readFileSync(route, 'utf8')
source = "import { stdProjectListDisplay } from '@/lib/stdProjectListDisplay'\n" + source
source = change(source, 'drive_folder_id,created_at,updated_at,submitted_at\')', "drive_folder_id,created_at,updated_at,submitted_at,saved_render_version:progress_payload->latest_render_version,saved_thumbnail_design_url:project_payload->thumbnail_design->>thumbnail_url')")
source = change(source, 'asset_type,status,drive_file_id,metadata\')', "asset_type,status,drive_file_id,metadata,created_at')")
source = change(source, '    const contextById = new Map(contexts.map(context => [context.id, context]))', "    const contextById = new Map(contexts.map(context => [context.id, context]))\n    if (projects.some(project => !contextById.has(project.id))) {\n        return NextResponse.json({ success: false, error: 'Could not load project completion status' }, { status: 503 })\n    }")
source = change(source, '                ...summary,', '                ...summary,\n                ...stdProjectListDisplay(project, context, assets.filter(asset => asset.project_id === project.id)),')
fs.writeFileSync(route, source)
for (const file of ['lib/stdProjectListDisplay.ts', 'lib/stdProjectStepStatus.ts']) fs.copyFileSync(path.join('auth-web', file), path.join(web, file))
console.log('Prepared isolated project list fixes')
