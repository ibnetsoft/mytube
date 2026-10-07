import { supabaseAdmin as db } from './supabaseAdmin'
import { aeMouthInput, currentAeMouthJob, reviewedAeMouthAssets } from './stdAeMouth'

export async function ensureAeMouthJob(project: any, scenes: any[], assets: any[], retry = false) {
    assets = [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    const { input, fingerprint } = aeMouthInput(project, scenes, assets)
    const existing = currentAeMouthJob(project, scenes, assets)
    if (existing && ['direction_pending', 'review_pending', 'failed'].includes(existing.metadata.state)) {
        const added = new Set(input.scenes.filter((scene: any) => scene.speaker_regions &&
            existing.metadata.input?.scenes?.some((old: any) => old.number === scene.number && !old.speaker_regions) &&
            existing.metadata.results?.some((result: any) => result.number === scene.number && result.status === 'needs_review')
        ).map((scene: any) => scene.number))
        if (added.size) {
            const metadata = { ...existing.metadata, state: 'queued', phase: 'discovery', error: null,
                input: { ...existing.metadata.input, scenes: existing.metadata.input.scenes.map((scene: any) =>
                    added.has(scene.number) ? input.scenes.find((next: any) => next.number === scene.number) : scene) },
                results: existing.metadata.results.filter((result: any) => !added.has(result.number)) }
            const updated = await db.from('std_project_assets').update({ metadata, updated_at: new Date().toISOString() })
                .eq('id', existing.id).eq('updated_at', existing.updated_at).select('*').maybeSingle()
            if (updated.error) throw updated.error
            if (!updated.data) throw new Error('AE 작업 상태가 변경되었습니다. 다시 확인해 주세요.')
            return { ready: false, job: updated.data }
        }
    }
    if (existing?.metadata?.state === 'reviewed') {
        reviewedAeMouthAssets({ ...project, project_payload: { ...project.project_payload, ae_mouth: { enabled: true } } }, scenes, assets)
        return { ready: true, job: existing }
    }
    if (existing && (!retry || existing.metadata.state !== 'failed')) return { ready: false, job: existing }
    if (retry && existing?.metadata?.state !== 'failed') throw new Error('실패한 작업만 재시도할 수 있습니다.')
    // Atomic storage claim also makes lost-response submission and concurrent retries idempotent.
    const path = `std/${project.id}/ae-mouth/${fingerprint}${retry ? '-' + existing.id : ''}.json`
    const claim = await db.storage.from('content-assets').upload(path, Buffer.from(JSON.stringify({ fingerprint })), { contentType: 'application/json', upsert: false })
    if (claim.error) {
        if (/already exists|duplicate|resource.*exist/i.test(claim.error.message || '')) return { ready: false, job: existing || null }
        throw claim.error
    }
    const inserted = await db.from('std_project_assets').insert({ project_id: project.id, asset_type: 'other', status: 'uploaded',
        file_name: `ae_mouth_${fingerprint}.json`, mime_type: 'application/json', metadata: { kind: 'ae_mouth_job', state: 'queued', fingerprint, input, results: [] },
    }).select('*').single()
    if (inserted.error) { await db.storage.from('content-assets').remove([path]); throw inserted.error }
    return { ready: false, job: inserted.data }
}
