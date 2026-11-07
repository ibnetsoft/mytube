export function motionOutputStatus(job: any) {
    const nativeWuxia = Boolean(job.required_worker_contract || job.input_worker_contract || job.state === 'awaiting_worker_update')
    const results = Array.isArray(job.results) ? job.results : []
    const count = job.state === 'awaiting_worker_update' ? 0 : nativeWuxia
        ? results.filter((r: any) => r.ambient_renderer === 'ambient_loop/v1' && r.adobe_flat_renderer === 'adobe_flat_scene/v1' && !r.source_passthrough).length
        : results.length
    return {
        native_wuxia: nativeWuxia,
        reviewed_scenes: count,
        error: job.state === 'awaiting_worker_update'
            ? '저장된 무협 연출을 실행하려면 렌더 워커 업데이트가 필요합니다. 원본과 음성은 보존되어 있습니다.'
            : job.error,
    }
}
