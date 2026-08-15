'use client'

import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Mic, RefreshCw, Upload } from 'lucide-react'
import { supabase } from '@/lib/supabaseClient'
import { isStdRequiredVideoScene, STD_REQUIRED_VIDEO_SCENE_COUNT } from '@/lib/stdPolicy'

type Topic = {
    id: number
    topic: string
    category_name: string
    language: string
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    scene_count: number
}

type StdProject = {
    id: string
    title: string
    status: string
    language: string
    assigned_duration_minutes: number | null
    estimated_payout: number | null
    drive_folder_id?: string | null
    progress_payload?: any
}

type SelectedProjectPayload = {
    project: StdProject & { project_payload?: any; review_notes?: string | null; reviewed_at?: string | null }
    scenes: any[]
    assets: any[]
}

const statusLabel: Record<string, string> = {
    claimed: '선택됨',
    in_progress: '작업중',
    assets_submitted: '에셋 제출',
    review_requested: '렌더 대기',
    approved: '승인',
    revision_requested: '수정 요청',
    rejected: '반려',
    canceled: '취소',
}

function assetLink(asset: any): string {
    return asset?.metadata?.web_view_link || `https://drive.google.com/file/d/${asset.drive_file_id}/view`
}

function imageGridPromptsFor(project: StdProject & { project_payload?: any }): any[] {
    const payload = project?.project_payload || {}
    const structure = payload.structure || {}
    const grids = Array.isArray(payload.image_grid_prompts)
        ? payload.image_grid_prompts
        : Array.isArray(structure.image_grid_prompts)
            ? structure.image_grid_prompts
            : []
    return grids
        .map((grid: any, index: number) => ({
            grid_number: grid?.grid_number || index + 1,
            scene_numbers: Array.isArray(grid?.scene_numbers) ? grid.scene_numbers : [],
            prompt: String(grid?.prompt || grid?.grid_prompt || '').trim(),
        }))
        .filter((grid: any) => grid.prompt && grid.scene_numbers.length === 4)
}

export default function StdPortalPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [token, setToken] = useState('')
    const [user, setUser] = useState<any>(null)
    const [topics, setTopics] = useState<Topic[]>([])
    const [projects, setProjects] = useState<StdProject[]>([])
    const [selectedProject, setSelectedProject] = useState<SelectedProjectPayload | null>(null)
    const [authChecking, setAuthChecking] = useState(true)
    const [loading, setLoading] = useState(false)
    const [projectLoading, setProjectLoading] = useState(false)
    const [uploadingKey, setUploadingKey] = useState('')
    const [generatingTts, setGeneratingTts] = useState(false)
    const [message, setMessage] = useState('')

    const authedJsonHeaders = useMemo(() => ({
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
    }), [token])

    const loadStdData = async (accessToken: string, options: { showLoading?: boolean } = {}) => {
        const showLoading = options.showLoading !== false
        if (showLoading) setLoading(true)
        setMessage('')
        try {
            const headers = { Authorization: `Bearer ${accessToken}` }
            const [meRes, topicsRes, projectsRes] = await Promise.all([
                fetch('/api/std/me', { headers }),
                fetch('/api/std/topics', { headers }),
                fetch('/api/std/projects', { headers }),
            ])
            const me = await meRes.json()
            const topicPayload = await topicsRes.json()
            const projectPayload = await projectsRes.json()
            if (!meRes.ok) throw new Error(me.error || 'STD 계정 확인 실패')
            setUser(me.user)
            setTopics(topicPayload.topics || [])
            setProjects(projectPayload.projects || [])
        } catch (error: any) {
            setMessage(error.message || '데이터를 불러오지 못했습니다.')
        } finally {
            if (showLoading) setLoading(false)
        }
    }

    useEffect(() => {
        supabase.auth.getSession()
            .then(async ({ data }) => {
                const accessToken = data.session?.access_token
                if (accessToken) {
                    setToken(accessToken)
                    await loadStdData(accessToken)
                }
            })
            .catch(() => {})
            .finally(() => setAuthChecking(false))
    }, [])

    const signIn = async () => {
        setLoading(true)
        setMessage('')
        try {
            const { data, error } = await supabase.auth.signInWithPassword({ email, password })
            if (error) throw error
            const accessToken = data.session?.access_token
            if (!accessToken) throw new Error('세션을 만들지 못했습니다.')
            setToken(accessToken)
            await loadStdData(accessToken)
        } catch (error: any) {
            setMessage(error.message || '로그인 실패')
        } finally {
            setLoading(false)
        }
    }

    const claimTopic = async (topicId: number) => {
        setLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/topics/${topicId}/claim`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await res.json()
            if (!res.ok) throw new Error(payload.error || '주제 선택 실패')
            setMessage('작업이 생성되었습니다.')
            await loadStdData(token)
        } catch (error: any) {
            setMessage(error.message || '주제 선택 실패')
        } finally {
            setLoading(false)
        }
    }

    const openProject = async (projectId: string) => {
        setProjectLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${projectId}`, {
                headers: { Authorization: `Bearer ${token}` },
            })
            const payload = await res.json()
            if (!res.ok) throw new Error(payload.error || '작업 조회 실패')
            setSelectedProject(payload)
        } catch (error: any) {
            setMessage(error.message || '작업 조회 실패')
        } finally {
            setProjectLoading(false)
        }
    }

    const reloadSelectedProject = async (options: { refreshLists?: boolean } = {}) => {
        if (!selectedProject?.project?.id) return
        await openProject(selectedProject.project.id)
        if (options.refreshLists) await loadStdData(token, { showLoading: false })
    }

    const uploadAsset = async (scene: any, assetType: 'image' | 'video', file: File | null) => {
        if (!file || !selectedProject) return
        const key = `${scene.scene_number}-${assetType}`
        setUploadingKey(key)
        setMessage('')
        try {
            const initRes = await fetch(`/api/std/projects/${selectedProject.project.id}/assets/init`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    scene_number: scene.scene_number,
                    asset_type: assetType,
                    file_name: file.name,
                    mime_type: file.type || (assetType === 'image' ? 'image/png' : 'video/mp4'),
                    file_size: file.size,
                }),
            })
            const initPayload = await initRes.json()
            if (!initRes.ok) throw new Error(initPayload.error || 'Drive 업로드 준비 실패')

            const uploadRes = await fetch(initPayload.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || initPayload.mime_type || 'application/octet-stream' },
                body: file,
            })
            const uploaded = await uploadRes.json().catch(() => ({}))
            if (!uploadRes.ok || !uploaded.id) {
                throw new Error(uploaded.error?.message || 'Drive 업로드 실패')
            }

            const completeRes = await fetch(`/api/std/projects/${selectedProject.project.id}/assets/complete`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({
                    scene_number: scene.scene_number,
                    asset_type: assetType,
                    drive_file_id: uploaded.id,
                    target_folder_id: initPayload.target_folder_id,
                    file_name: file.name,
                    mime_type: file.type,
                    file_size: file.size,
                }),
            })
            const completePayload = await completeRes.json()
            if (!completeRes.ok) throw new Error(completePayload.error || '업로드 등록 실패')

            setMessage(`Scene ${scene.scene_number} ${assetType === 'image' ? '이미지' : '영상'} 업로드 완료`)
            await reloadSelectedProject()
        } catch (error: any) {
            setMessage(error.message || '업로드 실패')
        } finally {
            setUploadingKey('')
        }
    }

    const submitProject = async () => {
        if (!selectedProject) return
        setLoading(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${selectedProject.project.id}/submit`, {
                method: 'POST',
                headers: authedJsonHeaders,
            })
            const payload = await res.json()
            if (!res.ok) {
                const missing = payload.missing_scene_numbers?.length
                    ? ` 누락 씬: ${payload.missing_scene_numbers.join(', ')}`
                    : ''
                throw new Error((payload.error || '제출 실패') + missing)
            }
            setMessage('렌더 큐에 제출되었습니다.')
            await reloadSelectedProject({ refreshLists: true })
        } catch (error: any) {
            setMessage(error.message || '제출 실패')
        } finally {
            setLoading(false)
        }
    }

    const generateTts = async () => {
        if (!selectedProject) return
        setGeneratingTts(true)
        setMessage('')
        try {
            const res = await fetch(`/api/std/projects/${selectedProject.project.id}/tts/generate`, {
                method: 'POST',
                headers: authedJsonHeaders,
                body: JSON.stringify({ provider: 'elevenlabs' }),
            })
            const payload = await res.json()
            if (!res.ok) throw new Error(payload.error || 'TTS 생성 실패')
            setMessage('TTS 오디오가 생성되어 Drive에 저장되었습니다.')
            await reloadSelectedProject()
        } catch (error: any) {
            setMessage(error.message || 'TTS 생성 실패')
        } finally {
            setGeneratingTts(false)
        }
    }

    const assetsByScene = useMemo(() => {
        const map = new Map<string, any[]>()
        for (const asset of selectedProject?.assets || []) {
            const key = String(asset.scene_number || '')
            map.set(key, [...(map.get(key) || []), asset])
        }
        return map
    }, [selectedProject])

    const audioAssets = useMemo(() => (
        (selectedProject?.assets || []).filter((asset: any) => asset.asset_type === 'audio' && ['uploaded', 'assigned'].includes(asset.status))
    ), [selectedProject])

    const imageGridPrompts = useMemo(
        () => selectedProject ? imageGridPromptsFor(selectedProject.project) : [],
        [selectedProject]
    )

    if (authChecking) {
        return (
            <main className="min-h-screen bg-[#f6f7f9] text-[#111827] flex items-center justify-center px-5">
                <section className="w-full max-w-sm border border-[#d9dde5] bg-white p-6 rounded-lg shadow-sm">
                    <div className="h-5 w-32 rounded bg-[#e5e7eb]" />
                    <div className="mt-4 h-3 w-full rounded bg-[#f1f5f9]" />
                    <div className="mt-2 h-3 w-2/3 rounded bg-[#f1f5f9]" />
                </section>
            </main>
        )
    }

    if (!token) {
        return (
            <main className="min-h-screen bg-[#f6f7f9] text-[#111827] flex items-center justify-center px-5">
                <section className="w-full max-w-sm border border-[#d9dde5] bg-white p-6 rounded-lg shadow-sm">
                    <h1 className="text-xl font-bold">AIR STD Web</h1>
                    <p className="mt-2 text-sm text-[#64748b]">STD 작업자 전용 웹 포털입니다.</p>
                    <div className="mt-6 space-y-3">
                        <input value={email} onChange={e => setEmail(e.target.value)} className="w-full border border-[#cbd5e1] px-3 py-2 rounded-md" placeholder="email" />
                        <input value={password} onChange={e => setPassword(e.target.value)} type="password" className="w-full border border-[#cbd5e1] px-3 py-2 rounded-md" placeholder="password" />
                        <button disabled={loading} onClick={signIn} className="w-full bg-[#2563eb] text-white py-2 rounded-md font-semibold disabled:opacity-50">로그인</button>
                    </div>
                    {message && <p className="mt-4 text-sm text-[#dc2626]">{message}</p>}
                </section>
            </main>
        )
    }

    return (
        <main className="min-h-screen bg-[#f6f7f9] text-[#111827]">
            <header className="border-b border-[#e5e7eb] bg-white px-6 py-4 flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold">AIR STD Web</h1>
                    <p className="text-sm text-[#64748b]">{user?.email}</p>
                </div>
                <button onClick={() => loadStdData(token)} disabled={loading} className="inline-flex items-center gap-2 border border-[#cbd5e1] px-3 py-2 rounded-md text-sm disabled:opacity-50">
                    <RefreshCw className="h-4 w-4" />
                    새로고침
                </button>
            </header>

            <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-5 p-5">
                <section className="space-y-5">
                    <div className="bg-white border border-[#e5e7eb] rounded-lg p-4">
                        <h2 className="font-bold">내 작업</h2>
                        <div className="mt-3 space-y-2">
                            {projects.map(project => (
                                <button key={project.id} disabled={projectLoading} onClick={() => openProject(project.id)} className="w-full text-left border border-[#e5e7eb] rounded-md p-3 hover:border-[#2563eb] disabled:opacity-50">
                                    <div className="font-semibold text-sm">{project.title}</div>
                                    <div className="text-xs text-[#64748b] mt-1">{statusLabel[project.status] || project.status} · {project.assigned_duration_minutes || '-'}분</div>
                                </button>
                            ))}
                            {!projects.length && <p className="text-sm text-[#94a3b8]">아직 생성된 작업이 없습니다.</p>}
                        </div>
                    </div>

                    <div className="bg-white border border-[#e5e7eb] rounded-lg p-4">
                        <h2 className="font-bold">선택 가능한 주제</h2>
                        <div className="mt-3 space-y-2">
                            {topics.map(topic => (
                                <div key={topic.id} className="border border-[#e5e7eb] rounded-md p-3">
                                    <div className="font-semibold text-sm">{topic.topic}</div>
                                    <div className="text-xs text-[#64748b] mt-1">{topic.category_name || 'No category'} · {topic.scene_count} scenes · {topic.assigned_duration_minutes || '-'}분</div>
                                    <button disabled={loading} onClick={() => claimTopic(topic.id)} className="mt-3 bg-[#111827] text-white px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-50">작업 선택</button>
                                </div>
                            ))}
                            {!topics.length && <p className="text-sm text-[#94a3b8]">준비 완료된 주제가 없습니다.</p>}
                        </div>
                    </div>
                </section>

                <section className="bg-white border border-[#e5e7eb] rounded-lg p-5 min-h-[620px]">
                    {message && <div className="mb-4 border border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8] px-3 py-2 rounded-md text-sm">{message}</div>}
                    {projectLoading && (
                        <div className="mb-4 border border-[#e5e7eb] bg-[#f8fafc] px-3 py-2 rounded-md text-sm text-[#64748b]">
                            작업 상세를 불러오는 중입니다.
                        </div>
                    )}
                    {!selectedProject ? (
                        <div>
                            <h2 className="text-lg font-bold">작업 상세</h2>
                            <p className="mt-2 text-sm text-[#64748b]">왼쪽에서 작업을 선택하면 준비된 대본, 프롬프트, 업로드 상태를 확인합니다.</p>
                        </div>
                    ) : (
                        <div>
                            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
                                <div>
                                    <h2 className="text-lg font-bold">{selectedProject.project.title}</h2>
                                    <p className="mt-1 text-sm text-[#64748b]">{statusLabel[selectedProject.project.status] || selectedProject.project.status} · {selectedProject.scenes.length} scenes</p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    <button onClick={generateTts} disabled={generatingTts || loading || selectedProject.project.status === 'review_requested'} className="inline-flex items-center justify-center gap-2 border border-[#cbd5e1] bg-white px-4 py-2 rounded-md text-sm font-semibold disabled:opacity-50">
                                        <Mic className="h-4 w-4" />
                                        {generatingTts ? 'TTS 생성 중' : 'TTS 생성'}
                                    </button>
                                    <button onClick={submitProject} disabled={loading || selectedProject.project.status === 'review_requested'} className="inline-flex items-center justify-center gap-2 bg-[#16a34a] text-white px-4 py-2 rounded-md text-sm font-semibold disabled:opacity-50">
                                        <CheckCircle2 className="h-4 w-4" />
                                        렌더 큐 제출
                                    </button>
                                </div>
                            </div>

                            {selectedProject.project.review_notes && (
                                <div className="mt-5 rounded-md border border-[#fed7aa] bg-[#fff7ed] p-3 text-sm text-[#9a3412]">
                                    <div className="font-semibold">검수 메모</div>
                                    <p className="mt-1 whitespace-pre-wrap">{selectedProject.project.review_notes}</p>
                                </div>
                            )}

                            <div className="mt-5">
                                <h3 className="font-bold">대본</h3>
                                <pre className="mt-2 whitespace-pre-wrap bg-[#f8fafc] border border-[#e5e7eb] rounded-md p-3 text-sm max-h-64 overflow-auto">{selectedProject.project.project_payload?.script || ''}</pre>
                            </div>

                            <div className="mt-5 rounded-md border border-[#e5e7eb] bg-[#f8fafc] p-3 text-sm">
                                <div className="font-bold">TTS 오디오</div>
                                {audioAssets.length > 0 ? (
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        {audioAssets.map((asset: any) => (
                                            <a key={asset.id} href={assetLink(asset)} target="_blank" rel="noreferrer" className="rounded-md bg-white border border-[#e5e7eb] px-2 py-1 text-xs text-[#334155] hover:bg-[#f1f5f9]">
                                                {asset.file_name}
                                            </a>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="mt-1 text-[#64748b]">렌더 큐 제출 전에 TTS를 생성해야 합니다.</p>
                                )}
                            </div>

                            <div className="mt-5 space-y-3">
                                <h3 className="font-bold">씬 프롬프트와 에셋 업로드</h3>
                                {imageGridPrompts.length > 0 && (
                                    <div className="mb-5 space-y-3">
                                        <h3 className="font-bold">2x2 이미지 생성 프롬프트</h3>
                                        {imageGridPrompts.map((grid: any) => (
                                            <div key={grid.grid_number} className="border border-[#e5e7eb] rounded-md p-3">
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="font-semibold text-sm">Grid {String(grid.grid_number).padStart(3, '0')}</div>
                                                    <div className="text-xs text-[#64748b]">Scenes {grid.scene_numbers.join(', ')}</div>
                                                </div>
                                                <textarea readOnly value={grid.prompt} className="mt-3 min-h-40 w-full border border-[#cbd5e1] rounded-md p-2 text-xs" />
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {selectedProject.scenes.map((scene: any) => {
                                    const sceneAssets = assetsByScene.get(String(scene.scene_number)) || []
                                    const isImageUploading = uploadingKey === `${scene.scene_number}-image`
                                    const isVideoUploading = uploadingKey === `${scene.scene_number}-video`
                                    const requiresVideo = isStdRequiredVideoScene(scene.scene_number)
                                    return (
                                        <div key={scene.id} className="border border-[#e5e7eb] rounded-md p-3">
                                            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                                                <div className="font-semibold text-sm">Scene {String(scene.scene_number).padStart(3, '0')} · {scene.scene_title}</div>
                                                {requiresVideo && (
                                                    <span className="rounded bg-[#ffedd5] px-2 py-0.5 text-[10px] font-bold text-[#c2410c]">
                                                        영상 필수
                                                    </span>
                                                )}
                                                <div className="text-xs text-[#64748b]">{scene.asset_status || 'missing'}</div>
                                            </div>
                                            <p className="mt-2 text-sm text-[#475569]">{scene.scene_text}</p>
                                            {requiresVideo && (
                                                <p className="mt-2 text-xs font-semibold text-[#c2410c]">
                                                    1-{STD_REQUIRED_VIDEO_SCENE_COUNT}번 씬은 영상 파일을 업로드해야 합니다.
                                                </p>
                                            )}
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                {!requiresVideo && (
                                                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[#cbd5e1] px-3 py-2 text-xs font-semibold hover:border-[#2563eb]">
                                                    <Upload className="h-4 w-4" />
                                                    {isImageUploading ? '이미지 업로드중' : '이미지 업로드'}
                                                    <input disabled={Boolean(uploadingKey)} type="file" accept="image/*" className="hidden" onChange={e => uploadAsset(scene, 'image', e.target.files?.[0] || null)} />
                                                </label>
                                                )}
                                                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[#cbd5e1] px-3 py-2 text-xs font-semibold hover:border-[#2563eb]">
                                                    <Upload className="h-4 w-4" />
                                                    {isVideoUploading ? '영상 업로드중' : '영상 업로드'}
                                                    <input disabled={Boolean(uploadingKey)} type="file" accept="video/*" className="hidden" onChange={e => uploadAsset(scene, 'video', e.target.files?.[0] || null)} />
                                                </label>
                                            </div>
                                            {sceneAssets.length > 0 && (
                                                <div className="mt-3 flex flex-wrap gap-2">
                                                    {sceneAssets.map((asset: any) => (
                                                        <a key={asset.id} href={assetLink(asset)} target="_blank" rel="noreferrer" className="rounded-md bg-[#f1f5f9] px-2 py-1 text-xs text-[#334155] hover:bg-[#e2e8f0]">
                                                            {asset.asset_type}: {asset.file_name}
                                                        </a>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}
                </section>
            </div>
        </main>
    )
}
