const PREPARATION = new Set(['ae_scene_preparation','ae_speaker_coordinates','region_layer_package'])

/** A user submission freezes a prepared package; it must not race preparation. */
export function assertPreparationFinished(assets:any[]) {
    const busy=assets.find(a=>a.metadata?.enabled!==false &&
        (PREPARATION.has(a.metadata?.kind)||(a.metadata?.kind==='motion_preview'&&a.metadata?.input?.task==='direction')) &&
        ['queued','processing'].includes(a.metadata?.state))
    if(busy)throw new Error('대본워커의 이미지·좌표·AE 연출 준비가 진행 중입니다. 준비가 끝난 뒤 유저웹에서 확인하고 제출하세요.')
}

export function assertPreparedMouthGeometry(input:any) {
    for(const scene of input.scenes||[]) {
        if(scene.ae_scene)continue
        const names=[...new Set((input.subtitles||[]).filter((r:any)=>r.scene_number===scene.number&&r.kind==='dialogue').map((r:any)=>r.speaker).filter(Boolean))]
        if(names.length&&(!scene.speaker_regions||names.some(name=>!scene.speaker_regions.speakers?.some((s:any)=>s.speaker===name))))
            throw new Error(`${scene.number}번 씬의 화자에 맞는 얼굴·입 좌표를 대본워커에서 준비한 뒤 제출하세요.`)
    }
}
