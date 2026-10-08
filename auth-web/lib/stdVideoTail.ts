export const VIDEO_TAIL_POLICY = 'normal_speed_ae_freeze_zoom_v1'

export function reviewedVideoTail(scene: any, source: any, payload: any) {
    if (!source || source.asset_type !== 'video') return source
    const number = Number(scene.scene_number)
    const rows = (payload?.subtitles || []).filter((r: any) => Number(r.scene_number) === number)
    const start = Math.min(...rows.map((r: any) => Number(r.start_num ?? r.start_time ?? r.start)))
    const end = Math.max(...rows.map((r: any) => Number(r.end_num ?? r.end_time ?? r.end)))
    const duration = end - start
    const sourceDuration = Number(source.metadata?.duration_seconds || scene.metadata?.duration_seconds || scene.duration_seconds)
    if (!Number.isFinite(duration) || !Number.isFinite(sourceDuration) || duration <= sourceDuration + 0.12) return source
    const saved = payload?.structure?.scenes?.find((s: any) => Number(s.scene_number || s.scene_order) === number)
    const tail = saved?.metadata?.ae_motion_asset || scene.metadata?.ae_motion_asset
    const sourcePath = source.metadata?.gcs_path || source.metadata?.storage_path
    const review = tail?.visual_review
    if (tail?.status !== 'ready' || tail?.video_tail_policy !== VIDEO_TAIL_POLICY
        || Math.abs(Number(tail.duration_seconds) - duration) > 0.12
        || !/^[0-9a-f]{64}$/.test(tail.render_sha256 || '') || review?.decision !== 'approved'
        || !review.reviewer || !review.note
        || review.render_sha256 !== tail.render_sha256
        || !sourcePath || tail.source_image?.object_path !== sourcePath
        || (source.metadata?.sha256 && tail.source_video_sha256 !== source.metadata.sha256)
        || !tail.gcs_bucket || !tail.gcs_path) {
        throw new Error(`${number}번 씬: 원본 영상은 ${sourceDuration.toFixed(1)}초, 자막은 ${duration.toFixed(1)}초입니다. 정상 속도 재생 후 마지막 화면 줌인 AE 작업과 검수를 완료해 주세요.`)
    }
    return { ...source, file_name: `scene_${number}_ae_tail.mp4`, mime_type: 'video/mp4', metadata: {
        ...source.metadata, storage_provider: 'gcs', gcs_bucket: tail.gcs_bucket, gcs_path: tail.gcs_path,
        duration_seconds: duration, video_tail_policy: VIDEO_TAIL_POLICY,
    } }
}
