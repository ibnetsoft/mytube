import { persistentThumbnailUrl } from './stdThumbnailUrl'

export function stdProjectListDisplay(project: any, context: any = {}, assets: any[] = []) {
    const payload = context.project_payload || project.project_payload || {}
    const progress = context.progress_payload || project.progress_payload || {}
    const thumbnail = assets.filter(asset => asset.asset_type === 'thumbnail' && ['uploaded', 'assigned'].includes(asset.status)
        && asset.id && (asset.metadata?.gcs_path || asset.metadata?.storage_path))
        .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    const thumbnail_url = persistentThumbnailUrl(progress.thumbnail_url, payload.thumbnail_url,
        project.saved_thumbnail_design_url, payload.thumbnail_design?.thumbnail_url,
        thumbnail ? `/api/std/projects/${encodeURIComponent(project.id)}/assets/file?assetId=${encodeURIComponent(thumbnail.id)}` : '')
    const version = Number(project.saved_render_version ?? project.latest_render_version ?? progress.latest_render_version)
    return { thumbnail_url, latest_render_version: Number.isSafeInteger(version) && version > 0 ? version : null }
}

export function projectListThumbnailUrl(value: unknown, impersonateEmail?: string | null): string {
    const url = persistentThumbnailUrl(value)
    if (!impersonateEmail || !url.startsWith('/api/std/')) return url
    const proxy = new URL(url, 'http://localhost')
    proxy.searchParams.set('impersonate', impersonateEmail)
    return proxy.pathname + proxy.search
}

// List completion is a persisted server snapshot, never an unsaved editor draft.
export function listedProjectStepStatus(project: any) {
    return project.step_status || {
        isTopicDone: false, isPlanningDone: false, isScriptDone: false,
        isImageDone: false, isTtsDone: false, isSubtitlesDone: false, isThumbnailDone: false,
        allDone: false, uploadedAssetsCount: 0, totalScenesCount: 0,
    }
}
