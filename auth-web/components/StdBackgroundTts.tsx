'use client'
import { useEffect, useRef } from 'react'
import { TtsNotice, ttsNoticeCopy } from './StdTtsNotice'

export default function StdBackgroundTts({ projectId, projectTitle, headers, locale, refreshKey, onBusy, onNotice, onComplete }: {
    projectId: string; projectTitle: string; headers: Record<string, string>; locale: string; refreshKey: number
    onBusy: (busy: boolean) => void; onNotice: (notice: TtsNotice) => void
    onComplete?: () => void
}) {
    const delivered = useRef('')
    const completion = useRef(onComplete)
    completion.current = onComplete
    useEffect(() => {
        if (!projectId) { onBusy(false); return }
        let stopped = false, timer: ReturnType<typeof setTimeout>
        const controller = new AbortController()
        const poll = async () => {
            try {
                const res = await fetch(`/api/std/projects/${projectId}/tts/jobs`, { headers, cache: 'no-store', signal: controller.signal })
                if (!res.ok) throw new Error('Status unavailable')
                const { job } = await res.json()
                if (stopped) return
                const active = job && ['queued', 'processing'].includes(job.status)
                onBusy(Boolean(active))
                if (job && (active || delivered.current !== job.id)) {
                    const copy = ttsNoticeCopy(locale)
                    onNotice({ projectId, projectTitle, background: true,
                        phase: active ? 'running' : job.status === 'completed' ? 'success' : 'error',
                        detail: active ? `${copy.progress(job.ready, job.total)}${job.ready === job.total ? ` · ${copy.assembling}` : ''}`
                            : job.status === 'completed' ? `${copy.saved} ${copy.counts(job.reused, job.generated)}` : job.error })
                    if (!active) {
                        delivered.current = job.id
                        if (job.status === 'completed') completion.current?.()
                    }
                }
            } catch (error) { if (stopped) return /* Network errors never cancel server work. */ }
            if (!stopped) timer = setTimeout(poll, 10000)
        }
        void poll()
        return () => { stopped = true; controller.abort(); clearTimeout(timer); onBusy(false) }
    }, [projectId, projectTitle, headers, locale, refreshKey, onBusy, onNotice])
    return null
}
