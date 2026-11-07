import { persistentThumbnailUrl } from './stdThumbnailUrl'

export function stdProjectListDisplay(project: any, context: any = {}, assets: any[] = []) {
    const payload = context.project_payload || project.project_payload || {}
    const progress = context.progress_payload || project.progress_payload || {}
    const thumbnail = assets.filter(asset => asset.asset_type === 'thumbnail' && ['uploaded', 'assigned'].includes(asset.status)
        && asset.id && (asset.metadata?.gcs_path || asset.metadata?.storage_path))
        .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    const scenes = [payload.scenes, payload.structure?.scenes, payload.pregenerated_structure?.scenes]
        .find(value => Array.isArray(value) && value.length) || []
    const scenePreview = scenes.map((scene: any) => persistentThumbnailUrl(scene.image_url)).find(Boolean)
    const candidates = [
        progress.thumbnail_url, payload.thumbnail_url,
        project.saved_thumbnail_design_url, payload.thumbnail_design?.thumbnail_url,
        thumbnail ? `/api/std/projects/${encodeURIComponent(project.id)}/assets/file?assetId=${encodeURIComponent(thumbnail.id)}` : '',
        project.saved_thumbnail_bg_url, payload.thumbnail_bg_url,
        project.saved_thumbnail_design_bg_url, payload.thumbnail_design?.bg_url, payload.thumbnail_design?.editor_bg_url,
        project.saved_progress_thumbnail_bg_url, progress.thumbnail_bg_url,
        project.saved_source_thumbnail_bg_url, project.source_payload?.thumbnail_bg_url,
        scenePreview,
    ].map(value => persistentThumbnailUrl(value)).filter(Boolean)
    const [thumbnail_url = '', ...thumbnail_fallback_urls] = [...new Set(candidates)]
    const version = Number(project.saved_render_version ?? project.latest_render_version ?? progress.latest_render_version)
    return { thumbnail_url, thumbnail_fallback_urls, latest_render_version: Number.isSafeInteger(version) && version > 0 ? version : null }
}

export function projectListThumbnailUrl(value: unknown, impersonateEmail?: string | null): string {
    const url = persistentThumbnailUrl(value)
    if (!url.startsWith('/api/std/')) return url
    const proxy = new URL(url, 'http://localhost')
    if (proxy.pathname === '/api/std/assets/gcs-file') proxy.searchParams.set('preview', '960')
    if (impersonateEmail) proxy.searchParams.set('impersonate', impersonateEmail)
    return proxy.pathname + proxy.search
}

// A broken final URL can still use the saved draft or a current scene preview.
export function projectListThumbnailCandidates(project: any, impersonateEmail?: string | null): string[] {
    return [...new Set([project.thumbnail_url, ...(Array.isArray(project.thumbnail_fallback_urls) ? project.thumbnail_fallback_urls : [])]
        .map(value => projectListThumbnailUrl(value, impersonateEmail)).filter(Boolean))]
}

export function advanceProjectListThumbnail(image: HTMLImageElement, candidates: string[]): void {
    const index = Number(image.dataset.fallbackIndex || 0) + 1
    image.dataset.fallbackIndex = String(index)
    if (candidates[index]) image.src = candidates[index]
    else image.hidden = true
}

// List completion is a persisted server snapshot, never an unsaved editor draft.
export function listedProjectStepStatus(project: any) {
    return project.step_status || {
        isTopicDone: false, isPlanningDone: false, isScriptDone: false,
        isImageDone: false, isTtsDone: false, isSubtitlesDone: false, isThumbnailDone: false,
        allDone: false, uploadedAssetsCount: 0, totalScenesCount: 0,
    }
}
